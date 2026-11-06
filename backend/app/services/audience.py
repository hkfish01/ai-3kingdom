"""觀眾助威／押陣：讓免登入的真人能參與，但不干預自主 agent。

設計原則（沿用賽季與校場演武的既有決策）：
- **不改 DB schema**：每日一個 `system_state` JSON bucket，30 天後自動清掉舊 bucket。
- **不改 agent 決策與數值**：助威只進「人望榜」，不進霸主積分；押陣只調整
  07:00 NPC 表演賽的「士氣係數」，不改兵力、金錢、聲望、勝場或 agent 任何欄位。
- **公開欄位限縮**：只回 agent id／name／城／兵力與票數，不回 owner、email、
  token、claim code；訪客識別碼只存不可逆雜湊，不存原始值。
- **輕量防刷**：瀏覽器自帶匿名 visitor_id，每個 HKT 日每種動作各一次。
  這能擋住誤觸與一般洗票，不是 Sybil 防護（清掉 localStorage 可重投），文件明說。

時段：HKT 07:00 之前投的票計入當日演武；之後投的計入隔日演武，
所以任何時間進來都有「下一場」可參與，不會有無法投票的空窗。
"""

from __future__ import annotations

import hashlib
import html
import io
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import exc as sa_exc
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Agent, SystemState
from .chronicle_card import (
    GOLD,
    HASHTAGS_EN,
    HASHTAGS_ZH,
    HEIGHT,
    MUTED,
    TEXT,
    WIDTH,
    BG,
    _draw_text,
    _font,
    _wrap_chars,
)
from .chronicle_publish import hkt_now
from .system_state import get_state

BUCKET_PREFIX = "audience.day."
KEEP_DAYS = 30
SIDES = ("challenger", "defender")
MAX_RETRIES = 3


def _key(date_str: str) -> str:
    return BUCKET_PREFIX + date_str


def _empty_bucket(date_str: str) -> dict[str, Any]:
    return {
        "date": date_str,
        "cheers": {},          # agent_id (str) -> count
        "votes": {"challenger": 0, "defender": 0},
        "visitors": {"cheer": [], "vote": []},  # irreversible hashes only
        "updated_at": "",
    }


def _load_bucket(db: Session, date_str: str) -> dict[str, Any]:
    raw = get_state(db, _key(date_str))
    try:
        data = json.loads(raw) if raw else _empty_bucket(date_str)
    except (json.JSONDecodeError, TypeError):
        data = _empty_bucket(date_str)
    if not isinstance(data, dict):
        return _empty_bucket(date_str)
    data.setdefault("cheers", {})
    data.setdefault("votes", {"challenger": 0, "defender": 0})
    data.setdefault("visitors", {"cheer": [], "vote": []})
    data["visitors"].setdefault("cheer", [])
    data["visitors"].setdefault("vote", [])
    return data


def _visitor_hash(visitor_id: str, date_str: str) -> str:
    """不可逆雜湊；salt 用既有 JWT secret，不新增金鑰、不存原始 visitor_id。"""
    raw = f"{visitor_id}:{date_str}:{settings.jwt_secret}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def target_date(now: datetime | None = None) -> str:
    """投票歸屬的 HKT 日期：07:00 前算當日，之後算隔日。"""
    hkt = hkt_now(now)
    day = hkt.date()
    if hkt.hour >= settings.arena_hour_hkt:
        day += timedelta(days=1)
    return day.isoformat()


def audience_date(now: datetime | None = None) -> str:
    return hkt_now(now).date().isoformat()


def _prune_old_buckets(db: Session, date_str: str) -> None:
    cutoff = _key((date.fromisoformat(date_str) - timedelta(days=KEEP_DAYS)).isoformat())
    (
        db.query(SystemState)
        .filter(SystemState.key.like(BUCKET_PREFIX + "%"), SystemState.key < cutoff)
        .delete(synchronize_session=False)
    )


def _record(
    db: Session,
    date_str: str,
    kind: str,
    visitor_id: str,
    mutate: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    """在同一個 row lock 裡完成「檢查＋寫入」，避免併發丟票。"""
    fingerprint = _visitor_hash(visitor_id, date_str)
    key = _key(date_str)
    for _attempt in range(MAX_RETRIES):
        try:
            row = (
                db.query(SystemState)
                .filter(SystemState.key == key)
                .with_for_update()
                .first()
            )
            if row is None:
                bucket = _empty_bucket(date_str)
                row = SystemState(key=key, value=json.dumps(bucket, ensure_ascii=False))
                db.add(row)
            else:
                bucket = _load_bucket(db, date_str)

            if fingerprint in bucket["visitors"][kind]:
                db.commit()
                return {"ok": False, "reason": "already_recorded", "date": date_str}

            mutate(bucket)
            bucket["visitors"][kind].append(fingerprint)
            bucket["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
            row.value = json.dumps(bucket, ensure_ascii=False)
            db.add(row)
            _prune_old_buckets(db, date_str)
            db.commit()
            return {"ok": True, "reason": None, "date": date_str, "bucket": bucket}
        except sa_exc.IntegrityError:
            # 兩個請求同時建立同一天的 bucket：讓 UNIQUE 決定勝負後重讀。
            db.rollback()
    return {"ok": False, "reason": "busy", "date": date_str}


def record_cheer(db: Session, visitor_id: str, agent_id: int, now: datetime | None = None) -> dict[str, Any]:
    date_str = target_date(now)

    def mutate(bucket: dict[str, Any]) -> None:
        key = str(agent_id)
        bucket["cheers"][key] = int(bucket["cheers"].get(key, 0)) + 1

    return _record(db, date_str, "cheer", visitor_id, mutate)


def record_vote(db: Session, visitor_id: str, side: str, now: datetime | None = None) -> dict[str, Any]:
    date_str = target_date(now)

    def mutate(bucket: dict[str, Any]) -> None:
        bucket["votes"][side] = int(bucket["votes"].get(side, 0)) + 1

    return _record(db, date_str, "vote", visitor_id, mutate)


def public_agents(db: Session, limit: int = 100) -> list[dict[str, Any]]:
    """可助威的諸侯；只回公開欄位，依兵力排序讓有人氣的先出現。"""
    rows = db.query(Agent).order_by(Agent.id.asc()).all()
    items = [
        {
            "agent_id": agent.id,
            "name": agent.name,
            "city": agent.current_city,
            "troops": (agent.infantry or 0) + (agent.archer or 0) + (agent.cavalry or 0),
        }
        for agent in rows
    ]
    items.sort(key=lambda row: (-row["troops"], row["agent_id"]))
    return items[:limit]


def cheer_standings(db: Session, date_str: str, limit: int = 8) -> list[dict[str, Any]]:
    bucket = _load_bucket(db, date_str)
    by_id = {row["agent_id"]: row for row in public_agents(db)}
    out = []
    for agent_key, count in bucket["cheers"].items():
        try:
            agent_id = int(agent_key)
        except (TypeError, ValueError):
            continue
        base = by_id.get(agent_id)
        if not base:
            continue  # agent 已被刪除，不讓孤兒資料進公開榜
        out.append({**base, "cheers": int(count)})
    out.sort(key=lambda row: (-row["cheers"], row["agent_id"]))
    return out[:limit]


def morale_for_date(db: Session, date_str: str) -> dict[str, Any]:
    """07:00 演武讀取：把押陣票轉成有限度的士氣係數。

    boost 範圍 ±AUDIENCE_MAX_BOOST，且總票數未達 AUDIENCE_MIN_VOTES 不生效；
    票數達 20 時才拿到完整幅度，避免單人洗票直接翻盤。
    """
    bucket = _load_bucket(db, date_str)
    challenger = int(bucket["votes"].get("challenger", 0) or 0)
    defender = int(bucket["votes"].get("defender", 0) or 0)
    total = challenger + defender
    cap = max(0.0, min(0.5, float(settings.audience_max_boost)))
    min_votes = max(1, int(settings.audience_min_votes))
    if total < min_votes or total == 0:
        boost = 0.0
    else:
        skew = (challenger - defender) / total
        participation = min(1.0, total / 20.0)
        boost = max(-cap, min(cap, skew * cap * participation))
    return {
        "challenger_votes": challenger,
        "defender_votes": defender,
        "total_votes": total,
        "boost": round(boost, 6),
        "boost_pct": round(boost * 100, 1),
        "applied": total >= min_votes,
        "cap_pct": round(cap * 100, 1),
        "min_votes": min_votes,
    }


def audience_rules(lang: str = "zh") -> dict[str, Any]:
    zh = lang != "en"
    cap = max(0.0, min(0.5, float(settings.audience_max_boost)))
    return {
        "one_per_day_zh": "每個 HKT 日、每個訪客可助威一次、押陣一次。",
        "one_per_day_en": "One cheer and one prediction per visitor per HKT day.",
        "target_zh": f"07:00 HKT 前投的票計入當日演武，之後計入隔日；上限 ±{round(cap * 100)}% 士氣。",
        "target_en": f"Votes before 07:00 HKT count for that day's exhibition; later votes roll to the next day. Cap: ±{round(cap * 100)}% morale.",
        "min_votes": max(1, int(settings.audience_min_votes)),
        "boost_cap_pct": round(cap * 100, 1),
        "full_participation_votes": 20,
        "exclusions_zh": "助威不計入霸主積分；士氣只影響 NPC 表演賽，不改諸侯兵力，也不替 agent 做決策。",
        "exclusions_en": "Cheers never affect season scores. Morale only touches the NPC exhibition; no agent stats change and no decisions are made for agents.",
        "note": (
            "匿名 visitor_id 只存不可逆雜湊，清除瀏覽器資料可重新投票，屬輕量防刷而非身分驗證。"
            if zh
            else "Anonymous visitor IDs are stored as irreversible hashes. Clearing browser data allows another vote; this is light abuse control, not identity verification."
        ),
    }


def today_snapshot(db: Session, lang: str = "zh", visitor_id: str | None = None, now: datetime | None = None) -> dict[str, Any]:
    date_str = audience_date(now)
    target = target_date(now)
    bucket = _load_bucket(db, target)
    fingerprint = _visitor_hash(visitor_id, target) if visitor_id else None
    cheers = sum(int(v) for v in bucket["cheers"].values())
    return {
        "enabled": settings.audience_enabled,
        "date": date_str,
        "target_date": target,
        "target_hour_hkt": settings.arena_hour_hkt,
        "already_cheered": bool(fingerprint and fingerprint in bucket["visitors"]["cheer"]),
        "already_voted": bool(fingerprint and fingerprint in bucket["visitors"]["vote"]),
        "cheer_total": cheers,
        "cheer_standings": cheer_standings(db, target),
        "votes": {
            "challenger": int(bucket["votes"].get("challenger", 0) or 0),
            "defender": int(bucket["votes"].get("defender", 0) or 0),
        },
        "morale": morale_for_date(db, target),
        "agents": public_agents(db),
        "rules": audience_rules(lang),
        "note": "Read-only audience layer: no agent stats are reset and no decisions are made for agents.",
    }


def card_payload(db: Session, lang: str = "zh", now: datetime | None = None) -> dict[str, Any]:
    target = target_date(now)
    snapshot = today_snapshot(db, lang, now=now)
    leaders = snapshot["cheer_standings"][:3]
    votes = snapshot["votes"]
    zh = lang != "en"
    headline = (
        f"【觀眾席・{target}】" if zh else f"[Audience - {target}]"
    )
    subtitle = (
        f"{snapshot['cheer_total']} 人助威・押陣 {votes['challenger']} : {votes['defender']}"
        if zh
        else f"{snapshot['cheer_total']} cheers - predictions {votes['challenger']}:{votes['defender']}"
    )
    lines = []
    for idx, row in enumerate(leaders, 1):
        label = f"{idx}. {row['name']}　{row['cheers']} 助威" if zh else f"{idx}. {row['name']} - {row['cheers']} cheers"
        lines.append(label)
    if not lines:
        lines.append("觀眾席尚靜，等你先喊一聲。" if zh else "The stands are quiet. Be the first to cheer.")
    return {
        "lang": "zh" if zh else "en",
        "date": target,
        "headline": headline,
        "subtitle": subtitle,
        "lines": lines,
        "footer": f"{settings.public_site_url.rstrip('/').replace('https://', '').replace('http://', '')}/audience",
    }


def build_audience_card_svg(payload: dict[str, Any]) -> str:
    esc = html.escape
    line_svg = "\n".join(
        f'<text x="80" y="{230 + i * 58}" font-size="30" fill="#e9eef6">{esc(line)}</text>'
        for i, line in enumerate(payload["lines"])
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
<rect width="{WIDTH}" height="{HEIGHT}" fill="#101a28"/>
<rect x="40" y="40" width="1120" height="550" rx="20" fill="none" stroke="#d9a441" stroke-opacity="0.45" stroke-width="2"/>
<text x="80" y="120" font-size="38" fill="#d9a441" font-weight="600">{esc(payload['headline'])}</text>
<text x="80" y="170" font-size="22" fill="#8fa2ba">{esc(payload['subtitle'])}</text>
{line_svg}
<text x="80" y="470" font-size="24" fill="#d9a441">{esc('免登入・每日一次・不替諸侯做決策' if payload['lang'] == 'zh' else 'No login - once a day - agents still decide for themselves')}</text>
<text x="80" y="570" font-size="20" fill="#8fa2ba">{esc(payload['footer'])}</text>
</svg>"""


def render_audience_card_png(payload: dict[str, Any]) -> bytes:
    """1200×630 人望榜分享卡；沒有 Pillow 時由呼叫端降級為 SVG。"""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((40, 40, 1160, 590), radius=20, outline=GOLD, width=2)
    _draw_text(draw, (80, 88), payload["headline"], _font(38), GOLD)
    _draw_text(draw, (80, 146), payload["subtitle"], _font(22), MUTED)
    for i, line in enumerate(payload["lines"]):
        _draw_text(draw, (80, 210 + i * 58), line, _font(30), TEXT)
    footer_text = (
        "免登入・每日一次・不替諸侯做決策"
        if payload["lang"] == "zh"
        else "No login - once a day - agents still decide for themselves"
    )
    for i, part in enumerate(_wrap_chars(footer_text, 34)[:1]):
        _draw_text(draw, (80, 440 + i * 40), part, _font(24), GOLD)
    _draw_text(draw, (80, 548), payload["footer"], _font(20), MUTED)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def audience_post_package(db: Session, lang: str = "zh", now: datetime | None = None) -> dict[str, Any]:
    """零憑證發文包：給人工貼 X／Threads／小紅書，或接既有 webhook。"""
    snapshot = today_snapshot(db, lang, now=now)
    zh = lang != "en"
    leaders = snapshot["cheer_standings"]
    top = leaders[0]["name"] if leaders else ("尚無人望" if zh else "no cheers yet")
    votes = snapshot["votes"]
    headline = (
        f"【觀眾席】{snapshot['cheer_total']} 人助威，{top} 最有人望"
        if zh
        else f"[Audience] {snapshot['cheer_total']} cheers; {top} leads the stands"
    )
    morale = (
        f"押陣 {votes['challenger']} : {votes['defender']}，士氣 {snapshot['morale']['boost_pct']:+.1f}%"
        if zh
        else f"Predictions {votes['challenger']}:{votes['defender']}, morale {snapshot['morale']['boost_pct']:+.1f}%"
    )
    link = f"{settings.public_site_url.rstrip('/')}/audience"
    hashtags = HASHTAGS_ZH if zh else HASHTAGS_EN
    caption = f"{headline}\n{morale}\n{link}\n{hashtags}"
    caption_long = "\n".join(
        [
            headline,
            "",
            morale,
            (f"生效於 {snapshot['target_date']} 07:00 HKT 校場演武。" if zh else f"Applies to the {snapshot['target_date']} 07:00 HKT exhibition."),
            snapshot["rules"]["exclusions_zh" if zh else "exclusions_en"],
            "",
            link,
            hashtags,
        ]
    )
    prefix = settings.chronicle_card_api_prefix.rstrip("/") or "/api"
    return {
        "type": "audience",
        "date": snapshot["date"],
        "target_date": snapshot["target_date"],
        "lang": "zh" if zh else "en",
        "headline": headline,
        "caption": caption,
        "caption_long": caption_long,
        "hashtags": hashtags,
        "image_url": f"{settings.public_site_url.rstrip('/')}{prefix}/world/public/audience/card.png?lang={'zh' if zh else 'en'}",
        "link": link,
        "share_text": caption,
        "cheer_total": snapshot["cheer_total"],
        "standings": leaders,
        "votes": votes,
        "morale": snapshot["morale"],
    }


def audience_note(db: Session, lang: str = "zh", now: datetime | None = None) -> str:
    """給 08:00 史記發文包的一行戰報：讀「當日」bucket，不是下一場的 bucket。"""
    day = audience_date(now)
    bucket = _load_bucket(db, day)
    cheers = sum(int(v) for v in bucket["cheers"].values())
    morale = morale_for_date(db, day)
    if cheers == 0 and morale["total_votes"] == 0:
        return ""
    zh = lang != "en"
    top = cheer_standings(db, day, limit=1)
    leader = top[0]["name"] if top else ""
    if zh:
        parts = [f"觀眾席今日 {cheers} 人助威"]
        if leader:
            parts.append(f"以 {leader} 最有人望")
        if morale["total_votes"]:
            parts.append(
                f"押陣 {morale['challenger_votes']}：{morale['defender_votes']}"
                f"（士氣 {morale['boost_pct']:+.1f}%）"
            )
        return "【觀眾席】" + "，".join(parts) + "。"
    parts = [f"{cheers} cheers from the stands today"]
    if leader:
        parts.append(f"{leader} leading")
    if morale["total_votes"]:
        parts.append(
            f"predictions {morale['challenger_votes']}:{morale['defender_votes']}"
            f" (morale {morale['boost_pct']:+.1f}%)"
        )
    return "[Audience] " + ", ".join(parts) + "."


def audience_status(db: Session) -> dict[str, Any]:
    target = target_date()
    return {
        "enabled": settings.audience_enabled,
        "target_date": target,
        "max_boost_pct": round(max(0.0, min(0.5, float(settings.audience_max_boost))) * 100, 1),
        "min_votes": max(1, int(settings.audience_min_votes)),
        "keep_days": KEEP_DAYS,
        "bucket": _load_bucket(db, target),
        "note": "Anonymous, one action per visitor per day; no agent state is modified.",
    }
