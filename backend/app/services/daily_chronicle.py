"""每日史記敘事層。

把 action_logs / battle_logs / messages / chronicles 的機械紀錄，
轉成人類可讀、可截圖轉貼的「史記」。

設計原則：
- 不需要 LLM 也能跑（確定性模板）；有設定 LLM 時才自動潤飾，失敗自動降級。
- 不新增資料表：寫入既有 chronicles，並把結構化故事存進 system_state。
- 對話預設不公開（隱私），需營運者明確設定 CHRONICLE_INCLUDE_DIALOGUE=true。
- collect / build 為唯讀，公開 API 可直接呼叫；只有 generate 會寫入。
- 同一天的重算採 upsert：覆寫當日那一則，不在公開史記裡堆重複的今日記事。
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import ActionLog, Agent, BattleLog, ChronicleEntry, City, Faction, Message
from .chronicle import write_chronicle
from .system_state import get_state, set_state
from .world_events import enrich_facts_with_events, event_lines

STORY_EVENT_TYPE = "daily_story"
LATEST_STORY_KEY = "chronicle_story_latest"
LAST_RUN_KEY = "chronicle_story_last_date"
# 記錄「未潤飾的模板內容」摘要，用來判斷當日局勢是否值得重算。
# 舊版本沒有這個 key：部署後第一輪會被視為 stale，自動把當日史記補齊。
STORY_SIGNATURE_KEY = "chronicle_story_signature"

# 這些是營運內部訊息，不適合出現在公開史記
HIDDEN_EVENT_TYPES = {"ai_devops_report"}

ACTION_LABELS_ZH = {
    "work": "務農與營生",
    "train": "練兵",
    "promote": "求官",
    "social": "往來遊說",
    "combat": "交鋒",
    "pve": "討伐",
    "pvp": "挑戰",
    "migrate": "遷徙",
    "rest": "休息",
}

ACTION_LABELS_EN = {
    "work": "economy",
    "train": "training",
    "promote": "promotion",
    "social": "diplomacy",
    "combat": "combat",
    "pve": "PVE",
    "pvp": "PVP",
    "migrate": "migration",
    "rest": "rest",
}


def _naive_utc() -> datetime:
    """SQLite DateTime 存的是 naive UTC，比較時必須去掉 tzinfo。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=None) if value.tzinfo else value


def _fmt(value: float | int) -> str:
    return f"{int(value):,}"


def _season_announcement_lines(db: Session, lang: str) -> list[str]:
    """賽季開季詔書／季末本紀：只帶最近 26 小時的公告，舊訊息不會永久卡在史記裡。

    賽季引擎把公告寫在 `system_state`；這裡純讀取，關閉賽季或沒有公告時回空陣列。
    """
    raw = get_state(db, "season.announcement")
    if not raw:
        return []
    try:
        data = json.loads(raw)
        created = datetime.fromisoformat(str(data["created_at"]))
        if created.tzinfo:
            created = created.replace(tzinfo=None)
        if _naive_utc() - created > timedelta(hours=26):
            return []
        return [str(line) for line in data.get("zh" if lang == "zh" else "en", [])][:2]
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return []


def _safe_quote(text: str, limit: int = 48) -> str:
    """避免把憑證、claim code 或過長內容放進公開圖卡。"""
    cleaned = " ".join((text or "").split())
    lowered = cleaned.lower()
    if any(token in lowered for token in ("claim code", "claim_code", "api key", "api_key", "sk-", "bearer ", "password")):
        return ""
    if "@" in cleaned and "." in cleaned:
        return ""
    return cleaned[:limit] + ("…" if len(cleaned) > limit else "")


def collect_daily_facts(db: Session, hours: int = 24) -> dict[str, Any]:
    """唯讀彙總。公開 API 可直接呼叫，不產生任何寫入。"""
    now = _naive_utc()
    since = now - timedelta(hours=hours)

    agents = db.query(Agent).all()
    names: dict[int, str] = {a.id: a.name for a in agents}
    agent_count = len(agents)
    richest = max(agents, key=lambda a: (a.gold, -a.id)) if agents else None
    strongest = max(agents, key=lambda a: (a.infantry + a.archer + a.cavalry, -a.id)) if agents else None
    faction_members = sum(1 for a in agents if a.faction_id is not None)
    new_agents = sum(1 for a in agents if (_as_naive(a.created_at) or since) >= since)

    faction_counts = {
        f.name: sum(1 for a in agents if a.faction_id == f.id)
        for f in db.query(Faction).all()
    }

    city_row = db.query(City).filter(City.name == settings.city_name).first()
    if not city_row:
        city_row = db.query(City).first()

    actions = db.query(ActionLog).filter(ActionLog.created_at >= since).all()
    action_counts = dict(Counter(a.action_type for a in actions))
    top_action = max(action_counts.items(), key=lambda kv: kv[1])[0] if action_counts else ""

    battles = (
        db.query(BattleLog)
        .filter(BattleLog.created_at >= since)
        .order_by(BattleLog.id.desc())
        .limit(50)
        .all()
    )
    battle_summaries = [
        {
            "attacker": names.get(b.attacker_agent_id or -1, "無名"),
            # 演武的對手是 NPC，不在 agents 表；明確標名，不要顯示成一般「守軍」。
            "defender": (
                "校場守軍"
                if b.defender_city == "校場:arena"
                else names.get(b.defender_agent_id or -1, "守軍")
            ),
            "exhibition": b.defender_city == "校場:arena",
            "outcome": b.outcome,
            "loot_gold": b.loot_gold,
            "battle_id": b.request_id,
        }
        for b in battles[:5]
    ]

    chronicle_count = (
        db.query(ChronicleEntry)
        .filter(ChronicleEntry.created_at >= since)
        .count()
    )

    quotes: list[dict[str, str]] = []
    if settings.chronicle_include_dialogue:
        rows = (
            db.query(Message)
            .filter(Message.created_at >= since, Message.message_type == "chat")
            .order_by(Message.id.desc())
            .limit(50)
            .all()
        )
        seen: set[str] = set()
        for row in rows:
            text = _safe_quote(row.content)
            if not text or text in seen:
                continue
            seen.add(text)
            quotes.append({"name": names.get(row.from_agent_id, "無名"), "text": text})
            if len(quotes) >= 2:
                break

    return {
        "city_name": city_row.name if city_row else settings.city_name,
        "treasury_gold": city_row.treasury_gold if city_row else 0,
        "treasury_food": city_row.treasury_food if city_row else 0,
        "agent_count": agent_count,
        "new_agents": new_agents,
        "richest": {"name": richest.name, "gold": richest.gold} if richest else None,
        "strongest": {
            "name": strongest.name,
            "troops": strongest.infantry + strongest.archer + strongest.cavalry,
        } if strongest else None,
        "factions": [{"name": k, "members": v} for k, v in sorted(faction_counts.items(), key=lambda kv: -kv[1])],
        "faction_members": faction_members,
        "actions_total": len(actions),
        "top_action": top_action,
        "action_counts": action_counts,
        "battles_total": len(battles),
        "battles": battle_summaries,
        "chronicle_count": chronicle_count,
        "quotes": quotes,
        "season_lines_zh": _season_announcement_lines(db, "zh"),
        "season_lines_en": _season_announcement_lines(db, "en"),
        "window_hours": hours,
        "collected_at": now.isoformat(),
    }


def _pick_aphorism(facts: dict[str, Any], zh: bool) -> str:
    """依局勢挑一句史官評語。刻意帶一點反諷，才值得被截圖。"""
    if zh:
        if facts["treasury_food"] == 0 and (facts["richest"] or {}).get("gold", 0) >= 10000:
            return "金滿倉，倉無糧；兵未滿百，已言天下。"
        if facts["battles_total"] >= 3:
            return "一夜數驚，勝者未得其利，敗者已記其仇。"
        if facts["faction_members"] <= 4 and facts["agent_count"] >= 10:
            return "天下三分，而三分皆虛位；諸侯多，肯選邊者少。"
        if facts["actions_total"] == 0:
            return "無事亦是事。史官只能記下滿城的沉默。"
        if facts["new_agents"] >= 5:
            return "新客盈門，舊盟未固；今日之友，未必是明日之臣。"
        return "城未動，心已動；史官姑且記之。"
    if facts["treasury_food"] == 0 and (facts["richest"] or {}).get("gold", 0) >= 10000:
        return "Gold fills the vault, the granary stands empty; fewer than a hundred troops, yet they speak of empire."
    if facts["battles_total"] >= 3:
        return "Three alarms in one night. The victors gained little; the defeated remembered everything."
    if facts["faction_members"] <= 4 and facts["agent_count"] >= 10:
        return "Three kingdoms, three empty thrones. Many lords, few who choose a side."
    if facts["actions_total"] == 0:
        return "Nothing happened. The scribe records a city holding its breath."
    return "The walls stand still; ambitions do not."


def build_story(facts: dict[str, Any], lang: str = "zh", date_str: str | None = None) -> dict[str, Any]:
    """把 facts 轉成結構化史記。純函式，方便測試。"""
    zh = lang == "zh"
    date_str = date_str or _naive_utc().date().isoformat()
    # 資料庫同時存在 洛阳 / Luoyang 兩種寫法；這裡只統一「顯示」，不動資料。
    raw_city = facts["city_name"]
    city = (
        {"洛阳": "洛陽", "Luoyang": "洛陽", "luoyang": "洛陽"}.get(raw_city, raw_city)
        if zh
        else {"洛阳": "Luoyang", "luoyang": "Luoyang"}.get(raw_city, raw_city)
    )
    headline = f"【史記・{date_str}　{city}】"

    lines: list[str] = []
    if zh:
        lines.append(
            f"{city}城現有 {_fmt(facts['agent_count'])} 位諸侯；"
            f"國庫存金 {_fmt(facts['treasury_gold'])}、糧 {_fmt(facts['treasury_food'])}。"
        )
        if facts["richest"]:
            lines.append(f"{facts['richest']['name']} 庫中存金 {_fmt(facts['richest']['gold'])}，居全城之首。")
        if facts["strongest"]:
            lines.append(f"握兵最多者為 {facts['strongest']['name']}，僅 {_fmt(facts['strongest']['troops'])} 人。")
        if facts["factions"]:
            joined = "、".join(f"{f['name']} {f['members']} 人" for f in facts["factions"][:3])
            lines.append(
                f"已成勢力者：{joined}，共 {_fmt(facts['faction_members'])} 人選邊；"
                f"其餘 {_fmt(max(0, facts['agent_count'] - facts['faction_members']))} 位仍在觀望。"
            )
        if facts["actions_total"]:
            label = ACTION_LABELS_ZH.get(facts["top_action"], facts["top_action"] or "行動")
            lines.append(f"過去一日共 {_fmt(facts['actions_total'])} 次動作，以「{label}」最多。")
        if facts["battles_total"]:
            first = facts["battles"][0]
            outcome = "攻方勝" if first["outcome"] == "attacker_win" else "守方勝"
            replay_hint = (
                f"（戰報見 /battle/replay/{first['battle_id']}）" if first.get("battle_id") else ""
            )
            opener = (
                "校場演武" if first.get("exhibition") else f"另有 {_fmt(facts['battles_total'])} 場交鋒"
            )
            lines.append(
                f"{opener}；{first['attacker']} 對 {first['defender']}，{outcome}，"
                f"掠金 {_fmt(first['loot_gold'])}。{replay_hint}"
            )
        else:
            lines.append("一日之內無人交兵，諸侯各自算計。")
    else:
        lines.append(
            f"{city} holds {_fmt(facts['agent_count'])} agents; "
            f"the treasury keeps {_fmt(facts['treasury_gold'])} gold and {_fmt(facts['treasury_food'])} food."
        )
        if facts["richest"]:
            lines.append(f"{facts['richest']['name']} holds {_fmt(facts['richest']['gold'])} gold, the most in the city.")
        if facts["strongest"]:
            lines.append(f"{facts['strongest']['name']} commands the largest force: {_fmt(facts['strongest']['troops'])} troops.")
        if facts["factions"]:
            joined = ", ".join(f"{f['name']} ({f['members']})" for f in facts["factions"][:3])
            lines.append(
                f"Factions: {joined}. {_fmt(facts['faction_members'])} agents have chosen a side; "
                f"{_fmt(max(0, facts['agent_count'] - facts['faction_members']))} remain uncommitted."
            )
        if facts["actions_total"]:
            label = ACTION_LABELS_EN.get(facts["top_action"], facts["top_action"] or "actions")
            lines.append(f"{_fmt(facts['actions_total'])} actions in the last day, mostly {label}.")
        if facts["battles_total"]:
            first = facts["battles"][0]
            replay_hint = (
                f" Replay /battle/replay/{first['battle_id']}" if first.get("battle_id") else ""
            )
            opener = (
                "Arena exhibition" if first.get("exhibition") else f"{_fmt(facts['battles_total'])} battles were fought"
            )
            lines.append(f"{opener}.{replay_hint}")
        else:
            lines.append("No battle today. Every lord is counting instead.")

    # 世界事件的局勢段落（稀缺／期限／背盟）。關閉時 facts 沒有這些 key，完全是加法。
    lines.extend(facts.get("event_lines_zh" if zh else "event_lines_en", [])[:3])
    # 賽季開季詔書／季末本紀：一樣是加法，沒有賽季或不啟用時不影響既有史記。
    lines.extend(facts.get("season_lines_zh" if zh else "season_lines_en", [])[:2])

    quotes = [
        {"name": q["name"], "text": q["text"]}
        for q in facts.get("quotes", [])
        if q.get("text")
    ]
    aphorism = _pick_aphorism(facts, zh)

    story: dict[str, Any] = {
        "date": date_str,
        "lang": "zh" if zh else "en",
        "city": city,
        "headline": headline,
        "lines": lines,
        "quotes": quotes,
        "aphorism": aphorism,
        "stats": {
            "agents": facts["agent_count"],
            "faction_members": facts["faction_members"],
            "actions": facts["actions_total"],
            "battles": facts["battles_total"],
            "treasury_gold": facts["treasury_gold"],
            "treasury_food": facts["treasury_food"],
        },
        "share_text": "",
    }
    story["share_text"] = compose_share_text(story)
    return story


def compose_share_text(story: dict[str, Any]) -> str:
    zh = story.get("lang") == "zh"
    parts = [story["headline"], *story["lines"]]
    for q in story.get("quotes", []):
        parts.append(f"{q['name']} 曰：「{q['text']}」" if zh else f'{q["name"]} said: "{q["text"]}"')
    parts.append("")
    parts.append(("史官曰：" if zh else "The scribe writes: ") + story["aphorism"])
    parts.append("")
    label = "AI 三國・今日史記" if zh else "AI Three Kingdoms - Daily Chronicle"
    parts.append(f"—— {label}　{settings.public_site_url.rstrip('/')}/chronicle")
    return "\n".join(parts)


def _polish_with_llm(story: dict[str, Any]) -> dict[str, Any]:
    """選配：用 OpenAI-compatible endpoint 潤飾，任何失敗都無聲降級為模板。"""
    if not (settings.chronicle_llm_endpoint and settings.chronicle_llm_api_key):
        return story
    zh = story.get("lang") == "zh"
    system = (
        "你是《三國志》的史官。把給定的客觀數據改寫成 3-5 句文言白話混雜的記事，"
        "語氣冷峻、略帶反諷，不得虛構人物、數字或事件。"
        "只回傳 JSON：{\"lines\": [\"...\"], \"aphorism\": \"...\"}。"
        if zh else
        "You are the court historian of an AI Three Kingdoms world. Rewrite the facts into 3-5 terse, "
        "slightly ironic chronicle lines. Never invent names, numbers or events. "
        "Return only JSON: {\"lines\": [\"...\"], \"aphorism\": \"...\"}."
    )
    try:
        response = httpx.post(
            settings.chronicle_llm_endpoint,
            headers={
                "Authorization": f"Bearer {settings.chronicle_llm_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.chronicle_llm_model or "gpt-4o-mini",
                "temperature": 0.7,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(story, ensure_ascii=False)},
                ],
            },
            timeout=15.0,
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return story
        data = json.loads(raw[start : end + 1])
        lines = [str(x) for x in data.get("lines", []) if str(x).strip()]
        aphorism = str(data.get("aphorism", "")).strip()
        if len(lines) >= 2 and aphorism:
            story["lines"] = lines[:5]
            story["aphorism"] = aphorism
            story["share_text"] = compose_share_text(story)
    except Exception:
        # 敘事層不能因為 LLM 掛了就跟著掛
        return story
    return story


def get_latest_story(db: Session) -> dict[str, Any] | None:
    raw = get_state(db, LATEST_STORY_KEY, default="")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def story_signature(story: dict[str, Any]) -> str:
    """用「讀者真正會看到的內容」算簽章，判斷當日史記是否過時。

    刻意排除 collected_at 之類的時間欄位，也比對未潤飾的模板版本：
    LLM 每次改寫措辭不該被誤判成局勢變了，否則會反覆寫入資料庫。
    """
    payload = {
        "headline": story.get("headline", ""),
        "lines": story.get("lines", []),
        "quotes": story.get("quotes", []),
        "aphorism": story.get("aphorism", ""),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _find_today_story_entry(db: Session, date_str: str) -> ChronicleEntry | None:
    """找出當日已寫入的 daily_story，讓重算可以覆寫而不是新增。"""
    day_start = datetime.fromisoformat(f"{date_str}T00:00:00")
    return (
        db.query(ChronicleEntry)
        .filter(
            ChronicleEntry.event_type == STORY_EVENT_TYPE,
            ChronicleEntry.created_at >= day_start,
        )
        .order_by(ChronicleEntry.id.desc())
        .first()
    )


def build_story_from_db(db: Session, lang: str = "zh") -> dict[str, Any]:
    """唯讀版本：給公開 API 在尚未產生當日史記時即時算出內容，不做任何寫入。"""
    return build_story(enrich_facts_with_events(db, collect_daily_facts(db)), lang=lang)


def build_weekly_situation(db: Session, lang: str = "zh") -> str:
    """注入 skill.md 的「本週局勢」。

    只給客觀處境，不給決策步驟 —— 這是讓 agent 產生意圖、而不是跑迴圈的關鍵。
    """
    facts = collect_daily_facts(db, hours=168)
    zh = lang == "zh"
    # 事件有期限，比排行榜數字更能讓 agent 產生「現在該做點什麼」的判斷。
    situation_lines = [f"- {line}" for line in event_lines(db, lang)]
    richest = (facts["richest"] or {}).get("name", "無")
    strongest = (facts["strongest"] or {}).get("name", "無")
    unaligned = max(0, facts["agent_count"] - facts["faction_members"])
    if zh:
        return "\n".join([
            f"- 城中現有 {_fmt(facts['agent_count'])} 位諸侯；國庫金 {_fmt(facts['treasury_gold'])}、糧 {_fmt(facts['treasury_food'])}。",
            f"- 已選邊 {_fmt(facts['faction_members'])} 人，仍有 {_fmt(unaligned)} 人未表態。",
            f"- 近七日共 {_fmt(facts['actions_total'])} 次動作、{_fmt(facts['battles_total'])} 場交鋒。",
            f"- 當今首富：{richest}；握兵最多：{strongest}。",
            *situation_lines,
            "- 以上是客觀事實，不是指令。接下來怎麼做，由你自己判斷。",
        ])
    return "\n".join([
        f"- {_fmt(facts['agent_count'])} agents in this city; treasury holds {_fmt(facts['treasury_gold'])} gold and {_fmt(facts['treasury_food'])} food.",
        f"- {_fmt(facts['faction_members'])} have chosen a faction; {_fmt(unaligned)} remain uncommitted.",
        f"- Last seven days: {_fmt(facts['actions_total'])} actions, {_fmt(facts['battles_total'])} battles.",
        f"- Richest: {richest}. Largest army: {strongest}.",
        *situation_lines,
        "- These are facts, not instructions. What you do next is your own decision.",
    ])


def generate_daily_chronicle(
    db: Session,
    lang: str = "zh",
    force: bool = False,
    date_str: str | None = None,
) -> dict[str, Any]:
    """寫入／重算一則當日史記。由 worker 每日觸發，或 admin 手動觸發。

    同一天重算時覆寫當日既有那一則（upsert），不新增 ChronicleEntry；
    否則每次局勢變動都會在公開史記裡堆一則長得差不多的今日記事。

    `date_str` 讓 08:00 HKT 的發文包可指定同一個 HKT 日期；00:00–08:00 HKT
    這段期間 UTC 日期會落後一天，若不指定，史記／圖卡日期會與發文包冪等鍵錯位。
    """
    today = date_str or _naive_utc().date().isoformat()
    if not force and get_state(db, LAST_RUN_KEY, default="") == today:
        cached = get_latest_story(db)
        if cached:
            return cached

    facts = enrich_facts_with_events(db, collect_daily_facts(db))
    story = build_story(facts, lang=lang, date_str=today)
    signature = story_signature(story)
    story = _polish_with_llm(story)

    entry = _find_today_story_entry(db, today)
    if entry is not None:
        entry.title = story["headline"]
        entry.content = story["share_text"]
        db.add(entry)
    else:
        write_chronicle(
            db,
            event_type=STORY_EVENT_TYPE,
            title=story["headline"],
            content=story["share_text"],
        )
    set_state(db, LATEST_STORY_KEY, json.dumps(story, ensure_ascii=False))
    set_state(db, STORY_SIGNATURE_KEY, signature)
    set_state(db, LAST_RUN_KEY, today)
    db.commit()
    return story


def refresh_today_story_if_stale(db: Session, now: datetime | None = None) -> dict[str, Any] | None:
    """當日史記重算：局勢變了就補寫，沒變就什麼都不做，回傳新史記或 None。

    典型情境：今日史記在 UTC 01:00 生成，事件引擎稍後才開啟／推進，
    或玩家捐糧、背盟讓局勢改觀 —— 公開觀戰不必等隔天才看得到。
    升級前產生的史記沒有簽章，會被視為 stale，部署後第一輪自動補齊。
    """
    current = _as_naive(now) or _naive_utc()
    today = current.date().isoformat()
    if get_state(db, LAST_RUN_KEY, default="") != today:
        # 當日還沒生過：交給 worker 的首次生成，不在這裡搶跑。
        return None

    latest = get_latest_story(db)
    lang = (latest or {}).get("lang", "zh")
    if lang not in {"zh", "en"}:
        lang = "zh"
    candidate = build_story(
        enrich_facts_with_events(db, collect_daily_facts(db)),
        lang=lang,
        date_str=today,
    )
    if story_signature(candidate) == get_state(db, STORY_SIGNATURE_KEY, default=""):
        return None
    return generate_daily_chronicle(db, lang=lang, force=True)
