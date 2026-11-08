"""每次優化都要有公告：版號、changelog、CHANGELOG.md、README 必須同步。"""

import json
import subprocess
import sys
from pathlib import Path

from app.config import settings

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent

TEXT_FIELDS = (
    "date", "version", "title_zh", "title_en", "detail_zh", "detail_en",
    "summary_zh", "summary_en", "agent_zh", "agent_en",
)
LIST_FIELDS = ("tags", "docs", "endpoints", "actions")


def _entries() -> list[dict]:
    return json.loads((BACKEND / "app" / "changelog.json").read_text(encoding="utf-8"))["entries"]


def test_version_files_are_in_sync_with_the_latest_announcement():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert settings.app_version == version
    assert _entries()[0]["version"] == version
    assert f"## {version}" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"**Current release:** `{version}`" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_every_release_has_fields_for_humans_and_agents():
    for entry in _entries():
        label = f"v{entry.get('version', '?')}"
        for key in TEXT_FIELDS:
            assert str(entry.get(key, "")).strip(), f"{label} missing {key}"
        for key in LIST_FIELDS:
            assert entry.get(key), f"{label} missing {key}"
        # 白話摘要不該只是把技術長文剪短。
        assert entry["summary_zh"] != entry["detail_zh"]
        assert entry["summary_en"] != entry["detail_en"]


def test_ci_release_notes_script_passes():
    result = subprocess.run(
        [sys.executable, str(BACKEND / "scripts" / "check_release_notes.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Release notes OK" in result.stdout
