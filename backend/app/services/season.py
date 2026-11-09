"""十四日賽季制：開季詔書、霸主積分、季末本紀與諸侯結局卡。

設計原則（沿用本專案既有決策）：
- **不改 DB schema**：賽季狀態、歷季歸檔、當日公告全部存 `system_state` 的 JSON；
  開季／季末本紀另外寫一則 `ChronicleEntry`，讓既有史記列表也看得到。
- **不重置玩家資料**：結算只讀 agent 快照，不改兵力、金錢、聲望、保護盾或 PVP 次數。
  賽季是排行榜與敘事層，既有玩法完全不受影響。
- **公開欄位限縮**：不回 owner、email、token、claim code 或 action payload。
- **演武不計戰績**：`arena_*` 的 NPC 表演賽不列入勝場，避免每日自動賽事刷分。
- **征伐不計戰績（1.36.0）**：`pve_*`／`PVE:` 的副本挑戰不列入勝場，且每位諸侯
  計入積分的勝場最多 20 場。舊規則「勝場×40 無上限」讓重複刷副本直接買下霸主；
  現在積分是即時計算，改公式就自動溯及本季所有歷史戰報，不需改 DB、不沒收存量。
- 開關 `SEASON_ENABLED`：Python 預設關閉（本機／CI 不製造資料），production compose 預設啟用。
"""

from __future__ import annotations

import html
import io
import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Agent, BattleLog, ChronicleEntry
from .chronicle_card import (
    BG,
    GOLD,
    HASHTAGS_EN,
    HASHTAGS_ZH,
    HEIGHT,
    MUTED,
    TEXT,
    WIDTH,
    _draw_text,
    _font,
    _wrap_chars,
)
from .chronicle_publish import hkt_now
from .system_state import get_state, set_state

CURRENT_KEY = "season.current"
ARCHIVE_PREFIX = "season.archive."
ARCHIVE_IDS_KEY = "season.archive.ids"
ANNOUNCEMENT_KEY = "season.announcement"

HKT = timezone(timedelta(hours=8))
DEFAULT_LENGTH_DAYS = 14


# ---------------------------------------------------------------------------
# 時間與狀態讀寫
# ---------------------------------------------------------------------------


def _hkt_date(now: datetime | None = None) -> date:
    return hkt_now(now).date()


def _hkt_day_start_utc_naive(day: date) -> datetime:
    """HKT 日界換成 SQLite/Postgres 裡的 naive UTC：當日 00:00 HKT = 前日 16:00 UTC。"""
    return datetime.combine(day, time.min) - timedelta(hours=8)


def _json_load(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw) if raw else fallback
    except (json.JSONDecodeError, TypeError):
        return fallback


# 1.36.0：勝場積分封頂。PvE 與校場演武已在 _season_wins 排除，這裡再擋一次
# 「靠大量有效 PvP 勝場無限放大積分」，同時讓公開榜的 wins 欄位等於計分勝場。
SEASON_WINS_CAP = 20


def load_current(db: Session) -> dict[str, Any]:
    return _json_load(get_state(db, CURRENT_KEY), {})


def load_archive(db: Session, season_id: str) -> dict[str, Any] | None:
    raw = get_state(db, ARCHIVE_PREFIX + season_id)
    data = _json_load(raw, None)
    return data if isinstance(data, dict) else None


def archive_ids(db: Session) -> list[str]:
    data = _json_load(get_state(db, ARCHIVE_IDS_KEY), [])
    return [str(x) for x in data] if isinstance(data, list) else []


def season_rules() -> dict[str, Any]:
    """公開勝利條件；前端直接顯示，不讓玩家猜分數怎麼算。"""
    return {
        "length_days": settings.season_length_days or DEFAULT_LENGTH_DAYS,
        "score_formula_zh": f"聲望×2 ＋ 兵力×3 ＋ 金÷100（上限100）＋ 糧÷200（上限50）＋ 計分勝場×40（上限{SEASON_WINS_CAP}場）＋ 已選邊＋20",
        "score_formula_en": f"reputation x2 + troops x3 + gold/100 (cap 100) + food/200 (cap 50) + scored wins x40 (cap {SEASON_WINS_CAP}) + faction +20",
        "wins_cap": SEASON_WINS_CAP,
        "wins_points": 40,
        "winner_zh": "赛季最後一個 HKT 日結束，翌日結算；積分最高者為霸主。同分先比聲望，再比兵力。",
        "winner_en": "Settled the day after the final HKT day. Highest score wins; ties break on reputation, then troops.",
        "exclusions_zh": "副本征伐與校場演武不計勝場；賽季不重置任何諸侯數值，也不替 agent 做決策。",
        "exclusions_en": "PvE dungeon runs and arena exhibitions do not count as wins. No agent stats are reset and no decisions are made for agents.",
    }


# ---------------------------------------------------------------------------
# 霸主積分與排行榜
# ---------------------------------------------------------------------------


def _season_wins(db: Session, start: date, end: date) -> dict[int, int]:
    """統計本季計分勝場；排除副本征伐（pve_*）與 NPC 校場演武（arena_*），並封頂。

    積分是每次查詢即時算出來的，沒有落地快取，所以規則一改就自動溯及本季
    所有歷史戰報（包含已發生的 1806 場副本勝利），不需要 migration 或回沖資料。
    """
    since = _hkt_day_start_utc_naive(start)
    until = _hkt_day_start_utc_naive(end + timedelta(days=1))
    rows = (
        db.query(BattleLog)
        .filter(BattleLog.created_at >= since, BattleLog.created_at < until)
        .all()
    )
    wins: dict[int, int] = {}
    for row in rows:
        request_id = row.request_id or ""
        defender_city = row.defender_city or ""
        if (
            request_id.startswith("arena_")
            or request_id.startswith("pve_")
            or defender_city.startswith("PVE:")
        ):
            continue
        if row.outcome == "attacker_win" and row.attacker_agent_id:
            wins[row.attacker_agent_id] = wins.get(row.attacker_agent_id, 0) + 1
        elif row.outcome == "defender_win" and row.defender_agent_id:
            wins[row.defender_agent_id] = wins.get(row.defender_agent_id, 0) + 1
    return {agent_id: min(count, SEASON_WINS_CAP) for agent_id, count in wins.items()}


def _score_agent(agent: Agent, wins: int) -> dict[str, Any]:
    troops = (agent.infantry or 0) + (agent.archer or 0) + (agent.cavalry or 0)
    gold = agent.gold or 0
    food = agent.food or 0
    reputation = agent.reputation or 0
    faction = 20 if agent.faction_id else 0
    parts = {
        "reputation": reputation * 2,
        "troops": troops * 3,
        "gold": min(max(gold, 0), 10000) // 100,
        "food": min(max(food, 0), 10000) // 200,
        "wins": wins * 40,
        "faction": faction,
    }
    return {
        "agent_id": agent.id,
        "name": agent.name,
        "city": agent.current_city or settings.city_name,
        "role": agent.role,
        "reputation": reputation,
        "troops": troops,
        "gold": gold,
        "food": food,
        "wins": wins,
        "faction": bool(agent.faction_id),
        "breakdown": parts,
        "score": sum(parts.values()),
    }


def _title(row: dict[str, Any], rank: int) -> tuple[str, str]:
    """依結局特徵給稱號；第一名的「霸主」優先。"""
    if rank == 1:
        return "霸主", "Hegemon"
    if row["wins"] >= 3:
        return "百戰之將", "Seasoned commander"
    if row["troops"] >= 100:
        return "擁兵自重", "Warlord"
    if row["gold"] >= 10000:
        return "富甲一方", "Merchant prince"
    if rank <= 3:
        return "一方諸侯", "Regional lord"
    if row["faction"]:
        return "開府建牙", "Faction retainer"
    if row["reputation"] >= 50:
        return "名滿洛陽", "Renowned in Luoyang"
    return "躬耕隴畝", "Quiet settler"


def _ending(row: dict[str, Any], rank: int, total: int, season_id: str) -> tuple[str, str]:
    title_zh, title_en = row["title_zh"], row["title_en"]
    if rank == 1:
        return (
            f"{season_id} 之季，{row['name']} 以 {row['score']} 分壓 {total} 位諸侯，定鼎洛陽。",
            f"In {season_id}, {row['name']} topped {total} lords with {row['score']} points.",
        )
    return (
        f"{row['name']} 列名第 {rank}，號「{title_zh}」；一季之內，勝 {row['wins']} 場、握兵 {row['troops']}。",
        f"{row['name']} finished #{rank} as {title_en}: {row['wins']} wins, {row['troops']} troops.",
    )


def _live_note(row: dict[str, Any]) -> tuple[str, str]:
    """賽季進行中的局勢句；結算語氣（定鼎／本紀）只能出現在歸檔與季末卡。"""
    if row["rank"] == 1:
        return (
            f"{row['name']} 以 {row['score']} 分暫居首位；霸主未定，諸侯仍可翻盤。",
            f"{row['name']} leads with {row['score']} points; the crown is still undecided.",
        )
    return (
        f"{row['name']} 列名第 {row['rank']}，號「{row['title_zh']}」；一季未終，勝負未定。",
        f"{row['name']} sits at #{row['rank']} as {row['title_en']}; the season is still open.",
    )


def standings(db: Session, season: dict[str, Any]) -> list[dict[str, Any]]:
    """即時排行榜；純讀取，不改任何 agent 資料。"""
    if not season:
        return []
    wins = _season_wins(db, date.fromisoformat(season["start_date"]), date.fromisoformat(season["end_date"]))
    rows = [_score_agent(a, wins.get(a.id, 0)) for a in db.query(Agent).all()]
    rows.sort(key=lambda r: (-r["score"], -r["reputation"], -r["troops"], r["agent_id"]))
    season_id = str(season["season_id"])
    total = len(rows)
    for idx, row in enumerate(rows, start=1):
        row["rank"] = idx
        row["total"] = total
        row["title_zh"], row["title_en"] = _title(row, idx)
        row["ending_zh"], row["ending_en"] = _ending(row, idx, total, season_id)
    return rows


def _chronicle_text(archive: dict[str, Any], lang: str = "zh") -> str:
    rows = archive.get("standings", [])
    winner = archive.get("winner") or {}
    runners = "、".join(str(r["name"]) for r in rows[1:4]) if len(rows) > 1 else ""
    if lang == "en":
        lines = [
            f"[Annals - Season {archive['index']} - {archive['start_date']} to {archive['end_date']}]",
            f"{archive['total_agents']} lords dwelt in the city. {winner.get('name', 'No one')} "
            f"took the throne with {winner.get('score', 0)} points.",
        ]
        if runners:
            lines.append(f"Next came {runners}.")
        lines.append(archive.get("aphorism_en", ""))
        return "\n".join(x for x in lines if x)
    lines = [
        f"【本紀・第 {archive['index']} 季（{archive['start_date']} ～ {archive['end_date']}）】",
        f"是季洛陽共 {archive['total_agents']} 位諸侯；"
        f"{winner.get('name', '無人')} 以 {winner.get('score', 0)} 分定鼎，號「霸主」。",
    ]
    if runners:
        lines.append(f"次為 {runners}；各據一方，成敗已入史冊。")
    lines.append(archive.get("aphorism_zh", ""))
    return "\n".join(x for x in lines if x)


def _aphorism(winner_score: int, total: int) -> tuple[str, str]:
    if total == 0:
        return "一季城空，史官擱筆。", "The city was empty; the scribe put down his brush."
    if winner_score == 0:
        return "一季無事，諸侯皆臥；不爭，亦是一種結局。", "Nothing happened. Even doing nothing is an ending."
    if winner_score < 100:
        return "天下未定，勝者不過先醒了一步。", "The realm is unsettled; the winner merely woke first."
    return "兵馬未歇，史冊已先記其名。", "The armies rest, but the annals already know the name."


# ---------------------------------------------------------------------------
# 開季 / 結算（寫入 system_state + chronicles，由 ensure_season 統一 commit）
# ---------------------------------------------------------------------------


def _set_announcement(db: Session, now: datetime, zh: list[str], en: list[str]) -> None:
    set_state(
        db,
        ANNOUNCEMENT_KEY,
        json.dumps(
            {
                "date": _hkt_date(now).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "zh": zh,
                "en": en,
            },
            ensure_ascii=False,
        ),
    )


def _open(db: Session, now: datetime, index: int) -> dict[str, Any]:
    start = _hkt_date(now)
    length = settings.season_length_days or DEFAULT_LENGTH_DAYS
    end = start + timedelta(days=max(1, length) - 1)
    state = {
        "season_id": f"s{start.strftime('%Y%m%d')}",
        "index": index,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "status": "active",
        "opened_at": datetime.now(timezone.utc).isoformat(),
    }
    set_state(db, CURRENT_KEY, json.dumps(state, ensure_ascii=False))
    db.add(
        ChronicleEntry(
            city_name=settings.city_name,
            event_type="season_open",
            title=f"開季詔書：第 {index} 季",
            content=(
                f"第 {index} 季起於 {start.isoformat()}，訖於 {end.isoformat()}；"
                f"十四日後按霸主積分定鼎，勝者入本紀。諸侯仍自行其事，史官照實而書。"
            ),
        )
    )
    return state


def _close(db: Session, state: dict[str, Any], now: datetime) -> dict[str, Any]:
    rows = standings(db, state)
    winner = rows[0] if rows else None
    aphorism_zh, aphorism_en = _aphorism(winner["score"] if winner else 0, len(rows))
    archive = {
        "season_id": state["season_id"],
        "index": state["index"],
        "start_date": state["start_date"],
        "end_date": state["end_date"],
        "closed_at": datetime.now(timezone.utc).isoformat(),
        "total_agents": len(rows),
        "winner": winner,
        "standings": rows,
        "aphorism_zh": aphorism_zh,
        "aphorism_en": aphorism_en,
        "chronicle_zh": "",
        "chronicle_en": "",
    }
    archive["chronicle_zh"] = _chronicle_text(archive, "zh")
    archive["chronicle_en"] = _chronicle_text(archive, "en")

    set_state(db, ARCHIVE_PREFIX + state["season_id"], json.dumps(archive, ensure_ascii=False))
    ids = [state["season_id"], *[x for x in archive_ids(db) if x != state["season_id"]]][:30]
    set_state(db, ARCHIVE_IDS_KEY, json.dumps(ids))
    db.add(
        ChronicleEntry(
            city_name=settings.city_name,
            event_type="season_close",
            title=f"季末本紀：第 {state['index']} 季",
            content=archive["chronicle_zh"],
        )
    )
    _ = now
    return archive


def ensure_season(
    db: Session,
    now: datetime | None = None,
    force_roll: bool = False,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """由 worker 每輪呼叫或 admin 手動推進；冪等，一天最多只會開／結一次。

    force_roll=True 會無視日期直接結算並開下一季，供營運與測試使用。
    """
    active = settings.season_enabled if enabled is None else enabled
    if not active:
        return {"action": "disabled", "enabled": False}

    today = _hkt_date(now)
    state = load_current(db)
    if not state:
        opened = _open(db, now or datetime.now(timezone.utc), 1)
        _set_announcement(
            db,
            now or datetime.now(timezone.utc),
            [f"【天下有事】開季詔書：第 1 季起於 {opened['start_date']}，十四日後定鼎（詳見 /season）。"],
            [f"[Decree] Season 1 opens {opened['start_date']}; the throne is decided in 14 days (/season)."],
        )
        db.commit()
        return {"action": "opened", "season": opened}

    expired = today > date.fromisoformat(state["end_date"])
    if not expired and not force_roll:
        return {"action": "none", "season": state}

    archive = _close(db, state, now or datetime.now(timezone.utc))
    opened = _open(db, now or datetime.now(timezone.utc), int(state["index"]) + 1)
    winner = archive.get("winner") or {}
    _set_announcement(
        db,
        now or datetime.now(timezone.utc),
        [
            f"【天下有事】季末本紀：第 {archive['index']} 季由 "
            f"{winner.get('name', '無人')} 以 {winner.get('score', 0)} 分定鼎（本紀見 /season）。",
            f"【天下有事】開季詔書：第 {opened['index']} 季即日起，十四日後再定天下。",
        ],
        [
            f"[Annals] Season {archive['index']} crowned {winner.get('name', 'nobody')} "
            f"with {winner.get('score', 0)} points (/season).",
            f"[Decree] Season {opened['index']} opens today; 14 days to the next crown.",
        ],
    )
    db.commit()
    return {
        "action": "rolled",
        "closed": {"season_id": archive["season_id"], "winner": winner.get("name"), "score": winner.get("score", 0)},
        "season": opened,
    }


# ---------------------------------------------------------------------------
# 公開資料
# ---------------------------------------------------------------------------


def season_history(db: Session, limit: int = 12) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for season_id in archive_ids(db)[:limit]:
        archive = load_archive(db, season_id)
        if not archive:
            continue
        winner = archive.get("winner") or {}
        items.append(
            {
                "season_id": season_id,
                "index": archive.get("index"),
                "start_date": archive.get("start_date"),
                "end_date": archive.get("end_date"),
                "total_agents": archive.get("total_agents", 0),
                "winner_name": winner.get("name"),
                "winner_score": winner.get("score", 0),
                "aphorism_zh": archive.get("aphorism_zh", ""),
                "aphorism_en": archive.get("aphorism_en", ""),
            }
        )
    return items


def season_summary(db: Session, lang: str = "zh") -> dict[str, Any]:
    """`/world/public/season/current` 的資料：倒數、領先榜、規則、上季摘要。"""
    state = load_current(db)
    rows = standings(db, state) if state else []
    days_left = None
    if state:
        days_left = (date.fromisoformat(state["end_date"]) - _hkt_date()).days + 1
    history = season_history(db, limit=1)
    previous = None
    if history:
        archive = load_archive(db, str(history[0]["season_id"]))
        if archive:
            previous = {
                **history[0],
                "chronicle": archive.get("chronicle_zh" if lang == "zh" else "chronicle_en", ""),
            }
    # 進行中的賽季不能講「定鼎」；歸檔快照才用結算語氣的結局句。
    leaders = rows[:10]
    for row in leaders:
        row["ending_zh"], row["ending_en"] = _live_note(row)
    return {
        "enabled": settings.season_enabled,
        "season": state or None,
        "days_left": days_left,
        "total_agents": len(rows),
        "leaderboard": leaders,
        "rules": season_rules(),
        "previous": previous,
        "history_count": len(archive_ids(db)),
        "note": "Read-only season layer: no agent stats are reset and no decisions are made for agents.",
    }


def ending_card_payload(
    db: Session,
    agent_id: int,
    season_id: str | None = None,
    lang: str = "zh",
) -> dict[str, Any] | None:
    """結局卡資料：可指定歷季（歸檔快照）或本季（即時積分），找不到就回 None。"""
    zh = lang != "en"
    if season_id:
        archive = load_archive(db, season_id)
        if not archive:
            return None
        row = next((r for r in archive.get("standings", []) if r["agent_id"] == agent_id), None)
        if not row:
            return None
        state = {
            "season_id": archive["season_id"],
            "index": archive["index"],
            "start_date": archive["start_date"],
            "end_date": archive["end_date"],
        }
        closed = True
    else:
        state = load_current(db)
        if not state:
            return None
        row = next((r for r in standings(db, state) if r["agent_id"] == agent_id), None)
        if not row:
            return None
        closed = False

    zh_note, en_note = _live_note(row)
    if closed:
        ending = row["ending_zh"] if zh else row["ending_en"]
    else:
        ending = zh_note if zh else en_note

    site = settings.public_site_url.rstrip("/")
    prefix = (settings.chronicle_card_api_prefix or "").rstrip("/")
    query = f"?agent_id={agent_id}&lang={'zh' if zh else 'en'}"
    if season_id:
        query += f"&season_id={season_id}"
    return {
        "season_id": state["season_id"],
        "index": state["index"],
        "start_date": state["start_date"],
        "end_date": state["end_date"],
        "closed": closed,
        "lang": "zh" if zh else "en",
        "agent_id": row["agent_id"],
        "agent_name": row["name"],
        "rank": row["rank"],
        "total": row["total"],
        "score": row["score"],
        "title": row["title_zh"] if zh else row["title_en"],
        "ending": ending,
        "reputation": row["reputation"],
        "troops": row["troops"],
        "gold": row["gold"],
        "food": row["food"],
        "wins": row["wins"],
        "city": row["city"],
        "links": {
            "season": f"{site}/season",
            "card_png": f"{prefix}/world/public/season/ending-card.png{query}",
            "card_svg": f"{prefix}/world/public/season/ending-card.svg{query}",
        },
    }


def ending_card_lines(payload: dict[str, Any]) -> tuple[str, str, str, list[str]]:
    """回傳 (標題, 副標題, 大字名號, 內文行)，PNG 與 SVG 共用。"""
    zh = payload["lang"] == "zh"
    season_id = payload["season_id"]
    headline = (
        f"【本紀・第 {payload['index']} 季　{season_id}】"
        if zh
        else f"[Annals - Season {payload['index']} - {season_id}]"
    )
    subtitle = (
        f"{payload['start_date']} ～ {payload['end_date']}　"
        + ("季末定鼎" if payload["closed"] else "賽季進行中")
        if zh
        else f"{payload['start_date']} to {payload['end_date']} - "
        + ("final" if payload["closed"] else "in progress")
    )
    name = f"第 {payload['rank']} 位／{payload['total']} 位　{payload['agent_name']}"
    if zh:
        body = [
            f"稱號「{payload['title']}」　霸主積分 {payload['score']}",
            f"聲望 {payload['reputation']}（×2）　兵力 {payload['troops']}（×3）",
            f"存金 {payload['gold']}　存糧 {payload['food']}　勝場 {payload['wins']}",
            f"所居 {payload['city']}　校場演武不計戰績",
        ]
    else:
        body = [
            f"{payload['title']} - score {payload['score']}",
            f"Reputation {payload['reputation']} (x2) - troops {payload['troops']} (x3)",
            f"Gold {payload['gold']} - food {payload['food']} - wins {payload['wins']}",
            f"City {payload['city']} - exhibitions excluded",
        ]
    return headline, subtitle, name, [line[:30] for line in body]


def build_ending_card_svg(payload: dict[str, Any]) -> str:
    esc = html.escape
    headline, subtitle, name, shown = ending_card_lines(payload)
    line_svg = "\n".join(
        f'<text x="80" y="{252 + i * 44}" font-size="23" fill="#e9eef6">{esc(line)}</text>'
        for i, line in enumerate(shown)
    )
    verdict = _wrap_chars(str(payload["ending"]), 26)[:2]
    verdict_svg = "\n".join(
        f'<text x="80" y="{470 + i * 44}" font-size="27" fill="#d9a441" font-weight="600">{esc(line)}</text>'
        for i, line in enumerate(verdict)
    )
    site = settings.public_site_url.rstrip("/").replace("https://", "").replace("http://", "")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
<rect width="{WIDTH}" height="{HEIGHT}" fill="#101a28"/>
<rect x="40" y="40" width="1120" height="550" rx="20" fill="none" stroke="#d9a441" stroke-opacity="0.45" stroke-width="2"/>
<text x="80" y="112" font-size="32" fill="#d9a441" font-weight="600">{esc(headline)}</text>
<text x="80" y="146" font-size="18" fill="#8fa2ba">{esc(subtitle)}</text>
<text x="80" y="206" font-size="34" fill="#e9eef6" font-weight="600">{esc(name)}</text>
{line_svg}
{verdict_svg}
<text x="80" y="590" font-size="18" fill="#8fa2ba">{esc(site)}/season</text>
</svg>"""


def render_ending_card_png(payload: dict[str, Any]) -> bytes:
    """1200×630 結局卡；沒有 Pillow／字型時由呼叫端降級為 SVG。"""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((40, 40, 1160, 590), radius=20, outline=GOLD, width=2)
    headline, subtitle, name, shown = ending_card_lines(payload)
    _draw_text(draw, (80, 78), headline, _font(32), GOLD)
    _draw_text(draw, (80, 128), subtitle, _font(18), MUTED)
    _draw_text(draw, (80, 172), name, _font(34), TEXT)
    for i, line in enumerate(shown):
        _draw_text(draw, (80, 226 + i * 44), line, _font(23), TEXT)
    for i, line in enumerate(_wrap_chars(str(payload["ending"]), 26)[:2]):
        _draw_text(draw, (80, 448 + i * 44), line, _font(27), GOLD)
    site = settings.public_site_url.rstrip("/").replace("https://", "").replace("http://", "")
    _draw_text(draw, (80, 566), f"{site}/season", _font(18), MUTED)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def season_post_package(db: Session, lang: str = "zh") -> dict[str, Any]:
    """賽季發文包：優先用上季結局，沒有歷季就用本季領先者。零憑證也能備料。"""
    zh = lang != "en"
    summary = season_summary(db, lang)
    history = season_history(db, limit=1)
    state = summary.get("season") or {}
    season_id = str(state.get("season_id", ""))
    payload = None
    closed = False

    if history:
        archive = load_archive(db, str(history[0]["season_id"]))
        winner = (archive or {}).get("winner") or {}
        if archive and winner:
            payload = ending_card_payload(db, int(winner["agent_id"]), str(archive["season_id"]), lang)
            season_id = str(archive["season_id"])
            closed = True
    if payload is None and summary.get("leaderboard"):
        payload = ending_card_payload(db, int(summary["leaderboard"][0]["agent_id"]), None, lang)

    link = f"{settings.public_site_url.rstrip('/')}/season"
    hashtags = HASHTAGS_ZH if zh else HASHTAGS_EN
    if payload is None:
        headline = "【賽季】洛陽開季，史官靜候" if zh else "[Season] The city opens, the scribe waits"
        caption = f"{headline}\n{link}\n{hashtags}"
        return {
            "type": "season",
            "date": _hkt_date().isoformat(),
            "lang": "zh" if zh else "en",
            "season_id": season_id,
            "closed": closed,
            "headline": headline,
            "caption": caption,
            "caption_long": caption,
            "image_url": "",
            "link": link,
            "hashtags": hashtags,
            "agent": None,
        }

    if closed:
        headline = (
            f"【季末本紀】第 {payload['index']} 季由 {payload['agent_name']} 定鼎・{payload['score']} 分"
            if zh
            else f"[Season finale] {payload['agent_name']} won season {payload['index']} with {payload['score']} points"
        )
    else:
        headline = (
            f"【賽季戰況】第 {payload['index']} 季剩 {summary['days_left']} 日，{payload['agent_name']} 暫居首位"
            if zh
            else f"[Season {payload['index']}] {summary['days_left']} days left; {payload['agent_name']} leads"
        )
    caption = "\n".join([headline, payload["ending"], "", link, hashtags])
    caption_long = "\n".join(
        [
            headline,
            "",
            payload["ending"],
            "",
            f"{payload['start_date']} ～ {payload['end_date']}" if zh else f"{payload['start_date']} to {payload['end_date']}",
            season_rules()["score_formula_zh" if zh else "score_formula_en"],
            "",
            link,
            hashtags,
        ]
    )
    return {
        "type": "season",
        "date": _hkt_date().isoformat(),
        "lang": "zh" if zh else "en",
        "season_id": season_id,
        "closed": closed,
        "headline": headline,
        "caption": caption,
        "caption_long": caption_long,
        "image_url": payload["links"]["card_png"],
        "link": link,
        "hashtags": hashtags,
        "agent": {
            "agent_id": payload["agent_id"],
            "name": payload["agent_name"],
            "rank": payload["rank"],
            "score": payload["score"],
            "title": payload["title"],
        },
    }


def season_status(db: Session) -> dict[str, Any]:
    return {
        "enabled": settings.season_enabled,
        "length_days": settings.season_length_days or DEFAULT_LENGTH_DAYS,
        "current": load_current(db) or None,
        "archive_count": len(archive_ids(db)),
        "archive_ids": archive_ids(db)[:10],
    }
