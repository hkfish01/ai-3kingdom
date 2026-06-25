#!/usr/bin/env python3
"""AI DevOps 主調度腳本"""
import os, sys, subprocess, json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()

def run_cmd(cmd, cwd=REPO_ROOT):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

def check_gh_auth():
    code, _, _ = run_cmd(["gh", "auth", "status"])
    return code == 0

def get_pending_prs():
    code, out, err = run_cmd(["gh", "search", "prs", "--repo", "hkfish01/ai-3kingdom", "--label", "ai-devops", "--state", "open", "--json", "number,title,body,url,author"])
    if code != 0:
        print(f"❌ 獲取 PR 失敗: {err}")
        return []
    try:
        return json.loads(out) if isinstance(json.loads(out), list) else []
    except:
        return []

def main():
    print("🚀 AI DevOps 自動化開始")
    print(f"📁 Repo: {REPO_ROOT}")
    if not check_gh_auth():
        print("❌ GitHub CLI 未登入")
        sys.exit(1)
    prs = get_pending_prs()
    print(f"📋 發現 {len(prs)} 個待處理 PR")
    if not prs:
        print("✅ 沒有需要處理的 PR")
        sys.exit(0)
    for pr in prs:
        pr_num = pr["number"]
        pr_title = pr["title"]
        pr_body = pr.get("body", "") or ""
        print(f"\n{'='*60}\n📦 處理 PR #{pr_num}: {pr_title}")
        print(f"\n🤖 Step 1: 調用 Kimi K2.7 生成代碼...")
        code, out, err = run_cmd(["python3", str(Path(__file__).parent / "kimi_coder.py"), "--pr", str(pr_num), "--body", pr_body])
        if code == 0:
            print(f"✅ Kimi 代碼生成完成")
        else:
            print(f"⚠️ Kimi 代碼生成失敗: {err}")
        print(f"\n🔍 Step 2: 調用 Cursor CLI 做代碼審查...")
        code, out, err = run_cmd(["python3", str(Path(__file__).parent / "cursor_reviewer.py"), "--pr", str(pr_num)])
        if code == 0:
            print(f"✅ Cursor 代碼審查完成")
        else:
            print(f"⚠️ Cursor 代碼審查失敗: {err}")
        print(f"✅ PR #{pr_num} 處理完成")
    print(f"\n{'='*60}\n🎉 AI DevOps 自動化完成")

if __name__ == "__main__":
    main()
