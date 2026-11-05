"""公開戰報回放：把既有 battle_logs 變成可播放的三回合分鏡與分享圖卡。

設計原則：
- 不改 DB schema、不改既有戰鬥邏輯。真實 PVE/PVP 與每日校場演武都走同一份回放規格。
- 公開欄位嚴格限縮：只回 agent 名字／城／戰力／勝負／戰利品，不回 owner、email、
  claim code 或 action payload。
- 分鏡資料來源優先讀 `arena.snapshot.<battle_id>`（演武的完整兵種快照），
  否則從既有 ActionLog.result_json 反推傷亡；兩者都沒有時仍能播出兵力條與勝負。
- 圖卡與文案是純函式，社群平台、og:image、08:00 發文包都能直接吃。
"""

from __future__ import annotations

import html
import io
import json
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..models import ActionLog, Agent, BattleLog
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
from .system_state import get_state

SNAPSHOT_PREFIX = "arena.snapshot."
TROOP_KEYS = ("infantry", "archer", "cavalry")

ACTION_LABELS = {
    "infantry_push": ("步兵推進", "Infantry push"),
    "archer_volley": ("弓矢齊發", "Archer volley"),
    "cavalry_charge": ("騎兵衝陣", "Cavalry charge"),
}

DUNGEON_NAMES = {
    "huangjin": "黃巾之亂",
    "hulao": "虎牢關",
    "chibi": "赤壁之戰",
}


def _empty_troops() -> dict[str, int]:
    return {key: 0 for key in TROOP_KEYS}


def _sum_troops(troops: dict[str, int]) -> int:
    return sum(max(0, int(troops.get(key, 0))) for key in TROOP_KEYS)


def _split_losses(losses: dict[str, int], rounds: int = 3) -> list[dict[str, int]]:
    """沿用既有 50/30/20 三回合分配，但把 `round()` 的累計誤差補回／扣回。

    既有登入端點容許總和差 1；公開回放的兵力條必須與戰報傷亡完全一致，
    所以這裡保證逐兵種、逐回合加總精準等於實際損失。
    """
    weights = [0.5, 0.3, 0.2][: max(1, rounds)]
    out = [_empty_troops() for _ in range(rounds)]
    for troop in TROOP_KEYS:
        total = max(0, int(losses.get(troop, 0)))
        for idx, weight in enumerate(weights):
            out[idx][troop] += int(round(total * weight))
        diff = total - sum(out[i][troop] for i in range(rounds))
        step = 0
        while diff != 0 and step < rounds * 10:
            idx = step % rounds
            if diff > 0:
                out[idx][troop] += 1
                diff -= 1
            elif out[idx][troop] > 0:
                out[idx][troop] -= 1
                diff += 1
            step += 1
    return out


def _dominant_label(troops: dict[str, int]) -> str:
    mapping = {
        "infantry": "infantry_push",
        "archer": "archer_volley",
        "cavalry": "cavalry_charge",
    }
    top = max(TROOP_KEYS, key=lambda k: troops.get(k, 0))
    return mapping[top]


def _label(action: str, zh: bool) -> str:
    pair = ACTION_LABELS.get(action)
    return pair[0 if zh else 1] if pair else action


def _parse_json(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _snapshot(db: Session, battle_id: str) -> dict[str, Any]:
    return _parse_json(get_state(db, SNAPSHOT_PREFIX + battle_id, default=""))


def _action_result(db: Session, battle_id: str) -> dict[str, Any]:
    """從既有 action_logs 反推傷亡；不做任何寫入。"""
    rows = (
        db.query(ActionLog)
        .filter(
            ActionLog.action_type.in_(
                ["pve_challenge", "pvp_challenge", "arena_exhibition"]
            )
        )
        .order_by(ActionLog.id.desc())
        .limit(300)
        .all()
    )
    for row in rows:
        payload = _parse_json(row.result_json)
        if payload.get("battle_id") == battle_id:
            return payload
    return {}


def _mode(battle_id: str) -> str:
    if battle_id.startswith("arena_"):
        return "arena"
    if battle_id.startswith("pve_"):
        return "pve"
    return "pvp"


def _agent_name(db: Session, agent_id: int | None, fallback: str) -> str:
    if not agent_id:
        return fallback
    agent = db.get(Agent, agent_id)
    return agent.name if agent else fallback


def _agent_troops(db: Session, agent_id: int | None) -> dict[str, int]:
    if not agent_id:
        return _empty_troops()
    agent = db.get(Agent, agent_id)
    if not agent:
        return _empty_troops()
    return {
        "infantry": agent.infantry or 0,
        "archer": agent.archer or 0,
        "cavalry": agent.cavalry or 0,
    }


def _defender_name(battle: BattleLog, db: Session, mode: str, zh: bool) -> str:
    if mode == "arena":
        return "校場守軍" if zh else "Arena garrison"
    if mode == "pve":
        dungeon_id = battle.defender_city.split(":", 1)[-1]
        name = DUNGEON_NAMES.get(dungeon_id, dungeon_id)
        return f"{name}守軍" if zh else f"{name} garrison"
    return _agent_name(db, battle.defender_agent_id, "守軍" if zh else "Defender")


def public_battle_item(db: Session, battle: BattleLog, lang: str = "zh") -> dict[str, Any]:
    """戰報列表的單筆公開欄位；不含任何帳號資訊。"""
    mode = _mode(battle.request_id)
    zh = lang == "zh"
    snapshot = _snapshot(db, battle.request_id)
    attacker = snapshot.get("attacker_name") or _agent_name(
        db, battle.attacker_agent_id, "無名" if zh else "Unknown"
    )
    defender = snapshot.get("defender_name") or _defender_name(battle, db, mode, zh)
    return {
        "battle_id": battle.request_id,
        "mode": mode,
        "exhibition": mode == "arena",
        "created_at": battle.created_at.isoformat() if battle.created_at else "",
        "attacker_name": attacker,
        "defender_name": defender,
        "attacker_city": battle.attacker_city,
        "defender_city": battle.defender_city,
        "attacker_power": round(battle.attack_power, 2),
        "defender_power": round(battle.defense_power, 2),
        "outcome": battle.outcome,
        "spoils": {"gold": battle.loot_gold or 0, "food": battle.loot_food or 0},
        "replay_url": f"/battle/replay/{battle.request_id}",
        "api_url": f"{settings.chronicle_card_api_prefix.rstrip('/')}/world/public/battle/replay/{battle.request_id}",
    }


def list_public_battles(db: Session, limit: int = 20, lang: str = "zh") -> list[dict[str, Any]]:
    rows = db.query(BattleLog).order_by(BattleLog.id.desc()).limit(limit).all()
    return [public_battle_item(db, row, lang) for row in rows]


def latest_public_battle(db: Session, lang: str = "zh") -> dict[str, Any] | None:
    row = db.query(BattleLog).order_by(BattleLog.id.desc()).first()
    return public_battle_item(db, row, lang) if row else None


def build_public_replay(db: Session, battle_id: str, lang: str = "zh") -> dict[str, Any] | None:
    """三回合分鏡：兵力條、回合字幕、勝負一句、分享連結。純讀取。"""
    battle = db.query(BattleLog).filter(BattleLog.request_id == battle_id).first()
    if not battle:
        return None

    zh = lang == "zh"
    mode = _mode(battle_id)
    snapshot = _snapshot(db, battle_id)
    result = _action_result(db, battle_id)

    attacker_name = snapshot.get("attacker_name") or _agent_name(
        db, battle.attacker_agent_id, "無名" if zh else "Unknown"
    )
    defender_name = snapshot.get("defender_name") or _defender_name(battle, db, mode, zh)

    attacker_losses = snapshot.get("losses") or result.get("losses") or _empty_troops()
    defender_losses = (
        snapshot.get("enemy_losses") or result.get("enemy_losses") or _empty_troops()
    )
    if mode == "pvp" and isinstance(result.get("losses"), dict) and "attacker" in result["losses"]:
        attacker_losses = result["losses"].get("attacker") or _empty_troops()
        defender_losses = result["losses"].get("defender") or _empty_troops()

    attacker_troops = snapshot.get("attacker_troops") or _agent_troops(db, battle.attacker_agent_id)
    defender_troops = snapshot.get("defender_troops") or _agent_troops(db, battle.defender_agent_id)
    if not _sum_troops(defender_troops):
        # 真實 PVE 的敵軍不在 agents 表；用戰力當兵力條基數，回放仍然成立。
        defender_troops = {"infantry": max(1, int(battle.defense_power)), "archer": 0, "cavalry": 0}

    attacker_base = max(1, _sum_troops(attacker_troops) or int(battle.attack_power))
    defender_base = max(1, _sum_troops(defender_troops))
    attacker_rounds = _split_losses(attacker_losses)
    defender_rounds = _split_losses(defender_losses)

    rounds: list[dict[str, Any]] = []
    remaining_a, remaining_d = attacker_base, defender_base
    for idx in range(3):
        a_action = _dominant_label(attacker_troops)
        d_action = _dominant_label(defender_troops)
        a_loss = _sum_troops(attacker_rounds[idx])
        d_loss = _sum_troops(defender_rounds[idx])
        remaining_a = max(0, remaining_a - a_loss)
        remaining_d = max(0, remaining_d - d_loss)
        if zh:
            caption = (
                f"第{idx + 1}回合・{_label(a_action, True)}："
                f"{attacker_name} 折損 {a_loss} 兵，{defender_name} 折損 {d_loss} 兵。"
            )
        else:
            caption = (
                f"Round {idx + 1} - {_label(a_action, False)}: "
                f"{attacker_name} lost {a_loss}, {defender_name} lost {d_loss}."
            )
        rounds.append(
            {
                "round": idx + 1,
                "attacker_action": a_action,
                "defender_action": d_action,
                "attacker_label": _label(a_action, zh),
                "defender_label": _label(d_action, zh),
                "casualties": {
                    "attacker": attacker_rounds[idx],
                    "defender": defender_rounds[idx],
                },
                "attacker_loss": a_loss,
                "defender_loss": d_loss,
                "attacker_remaining": remaining_a,
                "defender_remaining": remaining_d,
                "caption": caption,
            }
        )

    attacker_win = battle.outcome == "attacker_win"
    spoils = f"掠金 {battle.loot_gold or 0}、糧 {battle.loot_food or 0}"
    if snapshot.get("verdict"):
        verdict = str(snapshot["verdict"])
    elif zh:
        verdict = (
            f"是役，{attacker_name} 以 {remaining_a} 兵"
            f"{'勝' if attacker_win else '敗'}，{defender_name} 收兵；{spoils}。"
        )
    else:
        verdict = (
            f"{attacker_name} {'won' if attacker_win else 'lost'} with "
            f"{remaining_a} troops remaining; loot gold={battle.loot_gold or 0}, food={battle.loot_food or 0}."
        )

    exhibition_note = (
        "校場演武・不計戰績，不更動諸侯兵力；諸侯仍自行決定是否出戰。"
        if zh
        else "Arena exhibition: no ranking or troop changes; agents still decide their own battles."
    )
    prefix = settings.chronicle_card_api_prefix.rstrip("/")
    site = settings.public_site_url.rstrip("/")
    return {
        "battle_id": battle_id,
        "mode": mode,
        "lang": "zh" if zh else "en",
        "exhibition": mode == "arena",
        "exhibition_note": exhibition_note if mode == "arena" else "",
        "date": (battle.created_at.date().isoformat() if battle.created_at else ""),
        "created_at": battle.created_at.isoformat() if battle.created_at else "",
        "summary": {
            "attacker_name": attacker_name,
            "defender_name": defender_name,
            "attacker_city": battle.attacker_city,
            "defender_city": battle.defender_city,
            "attacker_power": round(battle.attack_power, 2),
            "defender_power": round(battle.defense_power, 2),
            "outcome": battle.outcome,
            "spoils": {"gold": battle.loot_gold or 0, "food": battle.loot_food or 0},
        },
        "combatants": {
            "attacker": {"name": attacker_name, "troops": attacker_base},
            "defender": {"name": defender_name, "troops": defender_base},
        },
        "rounds": rounds,
        "verdict": verdict,
        "links": {
            "replay": f"{site}/battle/replay/{battle_id}",
            "card_png": f"{site}{prefix}/world/public/battle/card.png?battle_id={battle_id}",
            "card_svg": f"{site}{prefix}/world/public/battle/card.svg?battle_id={battle_id}",
        },
    }


def battle_card_lines(replay: dict[str, Any]) -> tuple[str, str, list[str]]:
    """回傳 (標題, 副標題, 內文行)，供 PNG 與 SVG 共用。"""
    zh = replay.get("lang") == "zh"
    summary = replay["summary"]
    headline = (
        f"【戰報・{replay['date']}　{summary['attacker_name']} 對 {summary['defender_name']}】"
        if zh
        else f"[Battle - {replay['date']} - {summary['attacker_name']} vs {summary['defender_name']}]"
    )
    subtitle = (
        "AI 三國・三回合回放　諸侯自行其事，史官照實而書"
        if zh
        else "AI Three Kingdoms - Three-round replay - the lords act, the scribe records"
    )
    body: list[str] = []
    for row in replay["rounds"]:
        body.extend(_wrap_chars(str(row["caption"]), 30))
    if replay.get("exhibition_note"):
        body.extend(_wrap_chars(str(replay["exhibition_note"]), 30))
    shown = body[:6]
    if len(body) > 6 and shown:
        shown[5] = f"{shown[5][:28]}…"
    return headline, subtitle, shown


def build_battle_card_svg(replay: dict[str, Any]) -> str:
    esc = html.escape
    headline, subtitle, shown = battle_card_lines(replay)
    line_svg = "\n".join(
        f'<text x="80" y="{178 + i * 44}" font-size="24" fill="#e9eef6">{esc(line)}</text>'
        for i, line in enumerate(shown)
    )
    verdict = _wrap_chars(str(replay["verdict"]), 26)[:2]
    verdict_svg = "\n".join(
        f'<text x="80" y="{470 + i * 44}" font-size="28" fill="#d9a441" font-weight="600">{esc(line)}</text>'
        for i, line in enumerate(verdict)
    )
    site = settings.public_site_url.rstrip("/").replace("https://", "").replace("http://", "")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
<rect width="{WIDTH}" height="{HEIGHT}" fill="#101a28"/>
<rect x="40" y="40" width="1120" height="550" rx="20" fill="none" stroke="#d9a441" stroke-opacity="0.45" stroke-width="2"/>
<text x="80" y="112" font-size="32" fill="#d9a441" font-weight="600">{esc(headline)}</text>
<text x="80" y="146" font-size="18" fill="#8fa2ba">{esc(subtitle)}</text>
{line_svg}
{verdict_svg}
<text x="80" y="590" font-size="18" fill="#8fa2ba">{esc(site)}/battle/replay/{esc(replay['battle_id'])}</text>
</svg>"""


def render_battle_card_png(replay: dict[str, Any]) -> bytes:
    """1200×630 戰報卡；沒有 Pillow／字型時由呼叫端降級為 SVG。"""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((40, 40, 1160, 590), radius=20, outline=GOLD, width=2)
    headline, subtitle, shown = battle_card_lines(replay)
    _draw_text(draw, (80, 78), headline, _font(32), GOLD)
    _draw_text(draw, (80, 128), subtitle, _font(18), MUTED)
    for i, line in enumerate(shown):
        _draw_text(draw, (80, 160 + i * 44), line, _font(24), TEXT)
    for i, line in enumerate(_wrap_chars(str(replay["verdict"]), 26)[:2]):
        _draw_text(draw, (80, 462 + i * 44), line, _font(28), GOLD)
    site = settings.public_site_url.rstrip("/").replace("https://", "").replace("http://", "")
    _draw_text(draw, (80, 566), f"{site}/battle/replay/{replay['battle_id']}", _font(18), MUTED)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def battle_post_package(replay: dict[str, Any]) -> dict[str, Any]:
    """戰報發文包：X／Threads 短文案、小紅書長文案、戰報卡網址、回放連結。"""
    zh = replay.get("lang") == "zh"
    summary = replay["summary"]
    hashtags = HASHTAGS_ZH if zh else HASHTAGS_EN
    link = replay["links"]["replay"]
    headline = (
        f"【今日戰報】{summary['attacker_name']} 對 {summary['defender_name']}"
        if zh
        else f"[Battle report] {summary['attacker_name']} vs {summary['defender_name']}"
    )
    caption_lines = [headline, replay["verdict"], ""]
    if zh:
        caption_lines.append(f"三回合回放 → {link}")
    else:
        caption_lines.append(f"Three-round replay → {link}")
    caption_lines.append(hashtags)
    caption = "\n".join(caption_lines)
    caption_long = "\n".join(
        [headline, "", *(str(r["caption"]) for r in replay["rounds"]), "", replay["verdict"], "", link, hashtags]
    )
    return {
        "type": "battle_report",
        "date": replay["date"],
        "lang": "zh" if zh else "en",
        "battle_id": replay["battle_id"],
        "headline": headline,
        "caption": caption,
        "caption_long": caption_long,
        "verdict": replay["verdict"],
        "hashtags": hashtags,
        "image_url": replay["links"]["card_png"],
        "link": link,
        "exhibition": bool(replay.get("exhibition")),
    }
