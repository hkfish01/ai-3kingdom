#!/usr/bin/env python3
"""
Cursor CLI 代碼審查器
"""

import os, sys, json, argparse, subprocess, re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
# 在 GitHub Actions 裡由 workflow 注入；本機執行時沿用預設 repo。
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY") or "hkfish01/ai-3kingdom"

def run_cmd(cmd, cwd=REPO_ROOT, timeout=300):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout, result.stderr

def get_pr_details(pr_number):
    code, out, err = run_cmd(["gh", "api", f"repos/{GITHUB_REPO}/pulls/{pr_number}"])
    if code != 0:
        # 最常見原因：workflow 未設定 GH_TOKEN，gh CLI 無法驗證。
        print(f"⚠️ gh api 取得 PR 失敗: {(err or out).strip()[:400]}")
        return None
    try:
        return json.loads(out)
    except Exception:
        print("⚠️ gh api 回傳不是合法 JSON")
        return None

def get_pr_files(pr_number):
    code, out, _ = run_cmd(["gh", "api", f"repos/{GITHUB_REPO}/pulls/{pr_number}/files"])
    if code != 0:
        return []
    try:
        return json.loads(out)
    except:
        return []

def get_pr_diff(pr_number):
    code, out, _ = run_cmd(["gh", "pr", "diff", str(pr_number), "--repo", GITHUB_REPO])
    return out if code == 0 else ""

def local_review(diff, files):
    issues = []
    for file_info in files:
        filename = file_info.get("filename", "")
        patch = file_info.get("patch", "")
        if not patch:
            continue
        lines = patch.split("\n")
        for i, line in enumerate(lines, 1):
            if "console.log" in line and not filename.endswith(".test."):
                issues.append({"severity": "warning", "file": filename, "line": f"L{i}", "type": "Style", "description": "發現 console.log 調用", "suggestion": "生產環境應移除或使用日誌框架"})
            if "TODO" in line or "FIXME" in line:
                issues.append({"severity": "suggestion", "file": filename, "line": f"L{i}", "type": "Style", "description": f"發現未完成的標記: {line.strip()[:50]}", "suggestion": "確保此 TODO 在上線前完成"})
    return json.dumps({"summary": f"發現 {len(issues)} 個問題（本地基礎檢查）", "issues": issues[:20], "praise": [], "needs_human_review": len(issues) > 5}, ensure_ascii=False)

def format_review_comment(review_data, pr_title):
    summary = review_data.get("summary", "無")
    issues = review_data.get("issues", [])
    praise = review_data.get("praise", [])
    needs_human = review_data.get("needs_human_review", False)
    comment = f"## 🔍 代碼審查報告\n\n### 📋 {pr_title}\n\n**{summary}**\n\n"
    if praise:
        comment += "### ✨ 表揚\n\n" + "\n".join([f"- {p}" for p in praise[:5]]) + "\n\n"
    if issues:
        comment += f"### 📝 發現 {len(issues)} 個問題\n\n"
        critical = [i for i in issues if i.get("severity") == "critical"]
        warnings = [i for i in issues if i.get("severity") == "warning"]
        suggestions = [i for i in issues if i.get("severity") == "suggestion"]
        if critical:
            comment += "#### 🔴 Critical\n\n" + "".join([f"- **{issue.get('file')}** @ {issue.get('line')}\n  - [{issue.get('type')}] {issue.get('description')}\n  - 💡 {issue.get('suggestion')}\n\n" for issue in critical[:5]])
        if warnings:
            comment += "#### 🟡 Warning\n\n" + "".join([f"- **{issue.get('file')}** @ {issue.get('line')}\n  - [{issue.get('type')}] {issue.get('description')}\n  - 💡 {issue.get('suggestion')}\n\n" for issue in warnings[:10]])
        if suggestions:
            comment += "#### 🔵 Suggestion\n\n" + "".join([f"- **{issue.get('file')}** @ {issue.get('line')}\n  - {issue.get('description')}\n\n" for issue in suggestions[:5]])
    comment += "---\n_由 AI DevOps (Cursor CLI) 自動審查_"
    if needs_human:
        comment += "\n\n⚠️ **建議人工 reviewer 進一步審查**"
    return comment

def post_comment(pr_number, body):
    code, _, err = run_cmd(["gh", "pr", "comment", str(pr_number), "--body", body, "--repo", GITHUB_REPO])
    if code != 0:
        # Fork PR 的 GITHUB_TOKEN 固定唯讀，留言失敗不應讓整支 check 失敗。
        print(f"⚠️ 留言失敗（審查本身已完成）: {err.strip()[:400]}")
        return False
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr", type=int, required=True)
    args = parser.parse_args()
    print(f"🔍 Cursor CLI 代碼審查器\n📋 PR #{args.pr}")
    pr_details = get_pr_details(args.pr)
    if not pr_details:
        print("❌ 無法獲取 PR 詳情（請確認已安裝 gh CLI、設定 GH_TOKEN，且具備 pull-requests: read）")
        sys.exit(1)
    pr_title = pr_details.get("title", "")
    print(f"📌 PR: {pr_title}")
    files = get_pr_files(args.pr)
    print(f"📁 變更文件: {len(files)} 個")
    diff = get_pr_diff(args.pr)
    print(f"📊 Diff 大小: {len(diff)} bytes")
    # 目前尚未實作 Cursor CLI 呼叫；過去此分支會讓 review_result 未被定義而拋 NameError。
    cursor_available = subprocess.run(["which", "cursor"], capture_output=True).returncode == 0
    if cursor_available:
        print("⚠️ 偵測到 Cursor CLI，但尚未串接，改用地端基礎分析...")
    else:
        print("⚠️ Cursor CLI 不可用，使用地端基礎分析...")
    review_result = local_review(diff, files)
    try:
        review_data = json.loads(review_result)
    except:
        review_data = {"summary": "審查完成", "issues": [], "praise": [], "needs_human_review": True}
    comment = format_review_comment(review_data, pr_title)
    if post_comment(args.pr, comment):
        print(f"✅ 審查結果已發布到 PR #{args.pr}")
    else:
        print("❌ 發布審查結果失敗")

if __name__ == "__main__":
    main()
