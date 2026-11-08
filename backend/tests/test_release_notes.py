"""每次優化都要有公告：版號、changelog、CHANGELOG.md、README 必須同步。"""

import json
import shutil
import subprocess
import sys
import tempfile
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


def test_ci_script_blocks_a_code_change_without_a_new_bulletin():
    """守門員自己也要被測：改了程式卻沒升版／缺人讀欄位都要擋下。

    只有 feature 分支的後續 commit 能用 --allow-same-version 放行；
    PR 與 main 的 push 一律不給這個豁免。
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for folder in ("backend/app", "backend/scripts", "frontend/app"):
            (root / folder).mkdir(parents=True, exist_ok=True)
        copies = {
            "VERSION": "VERSION",
            "CHANGELOG.md": "CHANGELOG.md",
            "README.md": "README.md",
            "backend/app/config.py": "backend/app/config.py",
            "backend/app/changelog.json": "backend/app/changelog.json",
            "backend/scripts/check_release_notes.py": "backend/scripts/check_release_notes.py",
        }
        for src, dest in copies.items():
            shutil.copyfile(ROOT / src, root / dest)

        def git(*args: str) -> None:
            subprocess.run(
                ["git", "-C", str(root), "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
                check=True,
                capture_output=True,
                text=True,
            )

        git("init", "-q")
        git("add", "-A")
        git("commit", "-qm", "base")
        (root / "backend/app/new_feature.py").write_text("# optimisation\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-qm", "code change without a release note")

        script = str(root / "backend/scripts/check_release_notes.py")

        def check(*flags: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [sys.executable, script, "--base", "HEAD^", *flags],
                cwd=root,
                capture_output=True,
                text=True,
            )

        strict = check()
        assert strict.returncode != 0
        assert "版號沒有提升" in strict.stdout + strict.stderr

        allowed = check("--allow-same-version")
        assert allowed.returncode == 0, allowed.stdout + allowed.stderr

        changelog_path = root / "backend/app/changelog.json"
        data = json.loads(changelog_path.read_text(encoding="utf-8"))
        del data["entries"][0]["summary_zh"]
        changelog_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        broken = check("--allow-same-version")
        assert broken.returncode != 0
        assert "summary_zh" in broken.stdout + broken.stderr
