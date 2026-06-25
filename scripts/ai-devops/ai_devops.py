#!/usr/bin/env python3
"""
AI DevOps 自動化主調度腳本
- 由 cron job 定時觸發
- 調用 Kimi K2.7 生成代碼
- 調用 Cursor CLI 做代碼審查
"""

import os
import sys
import subprocess
import json
from pathlib import Path

# 專案根目錄
REPO_ROOT = Path(__file__).parent.parent.parent.resolve()

def run_cmd(cmd: list[str], cwd: Path = REPO_ROOT) -> tuple[int, str, str]:
    """執行 shell 命令"""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True
    )
    return result.returncode, result.stdout, result.stderr

def check_gh_auth() -> bool:
    """檢查 GitHub CLI 是否已登入"""
    code, out, _ = run_cmd(["gh", "auth", "status"])
    return code == 0

def get_pending_prs() -> list[dict]:
    """獲取待處理的 PR（帶 ai-devops label）"""
    # 使用 gh search 獲取 PR
    code, out, err = run_cmd([
        "gh", "search", "prs",
        "--repo", "hkfish01/ai-3kingdom",
        "--label", "ai-devops",
        "--state", "open",
        "--json", "number,title,body,url,author"
    ])
    
    if code != 0:
        print(f"❌ 獲取 PR 失敗: {err}")
        return []
    
    try:
        data = json.loads(out)
        # gh search prs --json 返回的是直接陣列
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        print(f"❌ 解析 PR 數據失敗: {out}")
        return []

def add_pr_comment(pr_number: int, body: str) -> bool:
    """在 PR 下留言"""
    code, _, err = run_cmd([
        "gh", "pr", "comment", str(pr_number),
        "--body", body
    ])
    if code != 0:
        print(f"❌ 留言失敗: {err}")
        return False
    return True

def main():
    print("🚀 AI DevOps 自動化開始")
    print(f"📁 Repo: {REPO_ROOT}")
    
    # 檢查 GitHub 認證
    if not check_gh_auth():
        print("❌ GitHub CLI 未登入，請先執行 `gh auth login`")
        sys.exit(1)
    
    # 獲取待處理 PR
    prs = get_pending_prs()
    print(f"📋 發現 {len(prs)} 個待處理 PR")
    
    if not prs:
        print("✅ 沒有需要處理的 PR")
        sys.exit(0)
    
    for pr in prs:
        pr_num = pr["number"]
        pr_title = pr["title"]
        pr_body = pr.get("body", "") or ""
        pr_url = pr["url"]
        
        print(f"\n{'='*60}")
        print(f"📦 處理 PR #{pr_num}: {pr_title}")
        print(f"🔗 {pr_url}")
        
        # Step 1: 用 Kimi K2.7 生成代碼
        print(f"\n🤖 Step 1: 調用 Kimi K2.7 生成代碼...")
        kimi_script = REPO_ROOT / "scripts/ai-devops/kimi_coder.py"
        code, out, err = run_cmd(["python3", str(kimi_script), "--pr", str(pr_num), "--body", pr_body])
        
        if code == 0:
            print(f"✅ Kimi 代碼生成完成")
            print(out)
        else:
            print(f"⚠️ Kimi 代碼生成失敗: {err}")
            add_pr_comment(pr_num, f"⚠️ **AI DevOps 錯誤**: Kimi K2.7 代碼生成失敗\n\n```\n{err}\n```")
        
        # Step 2: 用 Cursor CLI 做代碼審查
        print(f"\n🔍 Step 2: 調用 Cursor CLI 做代碼審查...")
        cursor_script = REPO_ROOT / "scripts/ai-devops/cursor_reviewer.py"
        code, out, err = run_cmd(["python3", str(cursor_script), "--pr", str(pr_num)])
        
        if code == 0:
            print(f"✅ Cursor 代碼審查完成")
            print(out)
        else:
            print(f"⚠️ Cursor 代碼審查失敗: {err}")
        
        print(f"✅ PR #{pr_num} 處理完成")
    
    print(f"\n{'='*60}")
    print("🎉 AI DevOps 自動化完成")

if __name__ == "__main__":
    main()
