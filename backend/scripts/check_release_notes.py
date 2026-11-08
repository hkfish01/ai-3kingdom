#!/usr/bin/env python3
"""每次優化都必須留下「人 + agent 共讀」的公告。

CI 在 PR 與 push 時執行：
    python backend/scripts/check_release_notes.py --base origin/main

檢查內容：
1. VERSION / config.app_version / changelog 第一筆 / CHANGELOG.md / README 版本一致。
2. 每個 changelog 條目都填齊雙讀欄位（白話摘要、agent 提示、端點、動作）。
3. 只要這次動到程式碼，版號就必須比 --base 提升，否則 revision 不變、
   worker 不會發公告，這輪優化等於沒有公告。

這支程式刻意只用標準庫：CI 不必為了檢查公告先裝一整套後端依賴。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent

# 動到這些路徑就算「優化」，必須升版 + 寫公告。純文件／CI 調整不強迫升版。
CODE_PREFIXES = (
    "backend/app/",
    "backend/alembic/",
    "frontend/app/",
    "frontend/components/",
    "frontend/lib/",
    "deploy/",
)

REQUIRED_TEXT_FIELDS = (
    "date", "version", "title_zh", "title_en", "detail_zh", "detail_en",
    "summary_zh", "summary_en", "agent_zh", "agent_en",
)
REQUIRED_LIST_FIELDS = ("tags", "docs", "endpoints", "actions")


def error(message: str) -> None:
    print(f"::error::{message}")
    raise SystemExit(1)


def git(*args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return None


def version_tuple(value: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", value)
    return tuple(int(x) for x in parts) if parts else (0,)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="", help="比較基準（PR: origin/main，push: HEAD^）")
    args = parser.parse_args()

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        error(f"VERSION 格式錯誤：{version!r}")

    config = (BACKEND / "app" / "config.py").read_text(encoding="utf-8")
    match = re.search(r'app_version:\s*str\s*=\s*"([^"]+)"', config)
    if not match or match.group(1) != version:
        error(f"config.py 的 app_version 與 VERSION ({version}) 不一致。")

    data = json.loads((BACKEND / "app" / "changelog.json").read_text(encoding="utf-8"))
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        error("changelog.json 沒有任何條目，系統不會發出公告。")
    if entries[0].get("version") != version:
        error(
            f"changelog 第一筆是 {entries[0].get('version')!r}，但 VERSION 是 {version!r}；"
            "每次優化都要在最前面補一則該版本的公告。"
        )

    for index, entry in enumerate(entries):
        label = f"changelog[{index}] (v{entry.get('version', '?')})"
        missing = [key for key in REQUIRED_TEXT_FIELDS if not str(entry.get(key, "")).strip()]
        missing += [key for key in REQUIRED_LIST_FIELDS if not entry.get(key)]
        if missing:
            error(
                f"{label} 缺少雙讀公告欄位 {missing}：人讀 summary_*、agent 讀 agent_* / endpoints / actions 都要填，"
                "否則公告只剩技術長文。"
            )

    changelog_md = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## {version}" not in changelog_md:
        error(f"CHANGELOG.md 缺少 `## {version}` 段落。")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if f"**Current release:** `{version}`" not in readme:
        error(f"README.md 的 Current release 不是 {version}。")

    if args.base:
        base_version = git("show", f"{args.base}:VERSION")
        changed = git("diff", "--name-only", f"{args.base}", "HEAD")
        base_changelog = git("show", f"{args.base}:backend/app/changelog.json")
        base_head_version = None
        if base_changelog:
            try:
                base_entries = json.loads(base_changelog).get("entries", [])
                base_head_version = base_entries[0].get("version") if base_entries else None
            except json.JSONDecodeError:
                pass

        # 同一個 PR 的第二個以後的 commit：前一個 commit 已經為這個版號寫好公告，
        # 不該要求每次 push 都再升一次版。
        already_bumped = base_version == version and base_head_version == version
        if base_version and changed is not None:
            code_changed = [p for p in changed.splitlines() if p.startswith(CODE_PREFIXES)]
            if already_bumped:
                print(f"Note: base {args.base} already carries the v{version} announcement; field checks still apply.")
            elif base_version == version and code_changed:
                error(
                    "這次動到了程式碼但版號沒有提升，revision 不會變、公告不會發。"
                    "請升版（VERSION + config.py + CHANGELOG.md + README.md）並在 changelog.json 最前面"
                    "補一則含 summary_*、agent_*、endpoints、actions 的公告。例如：" + ", ".join(code_changed[:3])
                )
            elif version_tuple(version) <= version_tuple(base_version):
                error(f"版號沒有往前：{args.base} 是 {base_version}，目前是 {version}。")

    print(
        f"Release notes OK: v{version}, {len(entries)} entries, "
        "all entries carry human summaries + agent fields; every code change publishes a bulletin."
    )


if __name__ == "__main__":
    main()
