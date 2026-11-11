"""首頁公告版面的防回歸檢查（1.36.1）。

這版是純顯示層調整，沒有新端點可以打，因此以靜態契約釘死三件事：
一打開就收起、整張卡片不超過 200px、給 agent 的完整公告一字不減。
"""

import json
import re
from pathlib import Path

from app.config import settings
from app.services import updates as updates_service

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "app" / "page.tsx"
CHANGELOG = ROOT / "backend" / "app" / "changelog.json"


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def _bulletin_section_classes() -> str:
    match = re.search(r'<section className="([^"]*max-h-\[200px\][^"]*)"', _page())
    assert match, "首頁公告卡片必須有 max-h-[200px]，否則更新又會撐長首頁"
    return match.group(1)


def test_bulletin_starts_collapsed():
    text = _page()
    assert re.search(
        r"announcementsOpen\s*,\s*setAnnouncementsOpen\]\s*=\s*useState\(false\)",
        text,
    ), "公告展開狀態必須預設 false（一打開就收起）"
    assert "aria-expanded={announcementsOpen}" in text
    assert 'aria-controls="home-announcements-body"' in text
    assert "setAnnouncementsOpen((open) => !open)" in text


def test_bulletin_card_is_capped_at_200px_and_scrolls_internally():
    classes = _bulletin_section_classes()
    for required in ("flex", "flex-col", "overflow-hidden"):
        assert required in classes, f"公告卡片缺少 {required}"

    body = re.search(r'id="home-announcements-body" className="([^"]+)"', _page())
    assert body, "公告內容區必須存在且可捲動"
    for required in ("min-h-0", "flex-1", "overflow-y-auto"):
        assert required in body.group(1), f"公告內容區缺少 {required}"

    # 收起時只留一行摘要，不渲染三則全文。
    assert "announcements.slice(0, 3)" in _page()
    assert "truncate text-xs" in _page()


def test_toggle_labels_exist_in_both_locales():
    text = _page()
    for key in (
        "announcementsExpand",
        "announcementsCollapse",
        "announcementsCount",
        "announcementsLatest",
    ):
        assert text.count(f"{key}:") == 2, f"{key} 必須中英各一份"


def test_web_still_crops_only_the_machine_block():
    text = _page()
    assert "humanAnnouncementText(item.content)" in text
    assert '"```agent-json"' in text or "'```agent-json'" in text
    assert "```agent-json" in text
    assert "/api/world/public/announcements" in text, "完整原文連結必須保留"


def test_release_bulletin_is_dual_audience_and_describes_the_layout_change():
    entries = json.loads(CHANGELOG.read_text(encoding="utf-8"))["entries"]
    latest = entries[0]
    assert latest["version"] == settings.app_version
    assert latest["summary_zh"] != latest["detail_zh"]
    assert latest["summary_en"] != latest["detail_en"]

    revision = updates_service.revision()
    _title, content = updates_service.render_announcement(latest, revision, "zh")
    human = updates_service.human_announcement_text(content)
    assert "【給人看 / For humans】" in human
    assert "展開" in human and "200px" in human
    assert "```agent-json" not in human, "網頁人讀段不該出現機器區塊"

    machine_json = content.split("```agent-json", 1)[1].split("```", 1)[0].strip()
    machine = json.loads(machine_json)
    assert machine["update_revision"] == revision
    assert "/world/public/announcements" in machine["endpoints"]
    assert any("Expand" in action or "expand" in action for action in machine["actions"])
    # 版面調整不能動到 agent 讀的端點集合：公告仍指同一批公開資源。
    assert "/world/public/updates" in machine["endpoints"]
