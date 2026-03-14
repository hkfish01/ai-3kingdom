import re


def localize_event_type(event_type: str, lang: str) -> str:
    if lang != "zh":
        return event_type
    mapping = {
        "agent": "代理",
        "faction": "勢力",
        "social": "社交",
        "diplomacy": "外交",
        "migration": "遷移",
        "battle": "戰鬥",
        "economy": "經濟",
        "military": "軍事",
        "federation": "聯邦",
        "federation_battle": "聯邦戰鬥",
        "daily_reset": "每日重置",
    }
    return mapping.get(event_type, event_type)


def localize_text(text: str, lang: str) -> str:
    if lang != "zh":
        return text
    out = text
    out = re.sub(r"^(.+?) registered$", r"\1 已註冊", out)
    out = re.sub(r"^(.+?) auto-bootstrapped$", r"\1 已自動初始化", out)
    out = re.sub(r"^Faction (.+?) founded$", r"勢力 \1 已建立", out)
    out = re.sub(r"^Peer connected: (.+)$", r"已連接聯邦節點：\1", out)
    out = re.sub(r"^Federation message from (.+)$", r"來自 \1 的聯邦訊息", out)
    out = re.sub(r"^(.+?) attacked (.+?)$", r"\1 攻擊了 \2", out)
    out = re.sub(r"^(.+?) completed (.+?)$", r"\1 完成了 \2", out)
    out = re.sub(r"^(.+?) trained (.+?) (.+?)$", r"\1 訓練了 \2 \3", out)
    out = re.sub(r"^(.+?) migrated$", r"\1 已遷移", out)
    out = re.sub(r"^(.+?) daily reset completed$", r"\1 每日重置完成", out)
    out = re.sub(r"joined city (.+?) as (.+?)\.", r"以 \2 身份加入城池 \1。", out)
    out = re.sub(r"is now vassal of (.+?)\.", r"現已成為 \1 的附庸。", out)
    out = re.sub(r"established faction (.+?) in (.+?)\.", r"在 \2 建立了勢力 \1。", out)
    out = re.sub(r"Outcome: victory\.", r"結果：勝利。", out)
    out = re.sub(r"Outcome: defeat\.", r"結果：失敗。", out)
    out = re.sub(r"Outcome: attacker_win\.", r"結果：進攻方勝利。", out)
    out = re.sub(r"Outcome: defender_win\.", r"結果：防守方勝利。", out)
    out = re.sub(r"Total power is now ([0-9.]+)\.", r"目前總戰力為 \1。", out)
    out = re.sub(r"Energy reset for (\d+) agents\.", r"已為 \1 名代理重置體力。", out)
    out = re.sub(r"Total upkeep food: (\d+)\.", r"總糧食維護消耗：\1。", out)
    out = re.sub(r"gained (\d+) gold and (\d+) food\.", r"獲得 \1 黃金與 \2 糧食。", out)
    out = re.sub(r"City tax gold: (\d+)\.", r"城市稅收黃金：\1。", out)
    out = re.sub(r"Role=(.+?), reputation=(.+)$", r"角色=\1，聲望=\2", out)
    return out
