#!/usr/bin/env python3
"""
Cursor CLI 代碼審查器
- 調用 Cursor CLI 做 PR 代碼審查
- 在 PR 下留言審查結果
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
GITHUB_REPO = "hkfish01/ai-3kingdom"

def run_cmd(cmd: list[str], cwd: Path = REPO_ROOT, timeout: int = 300) -> tuple[int, str, str]:
    """執行 shell 命令"""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout
    )
    return result.returncode, result.stdout, result.stderr

def get_pr_details(pr_number: int) -> Optional[dict]:
    """獲取 PR 詳情"""
    code, out, err = run_cmd([
        "gh", "api", f"repos/{GITHUB_REPO}/pulls/{pr_number}",
        "--jq", "."  # 輸出完整 JSON
    ])
    
    if code != 0:
        print(f"❌ 獲取 PR 詳情失敗: {err}")
        return None
    
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None

def get_pr_files(pr_number: int) -> list[dict]:
    """獲取 PR 變更的文件"""
    code, out, err = run_cmd([
        "gh", "api", f"repos/{GITHUB_REPO}/pulls/{pr_number}/files"
    ])
    
    if code != 0:
        print(f"❌ 獲取 PR 文件失敗: {err}")
        return []
    
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return []

def get_pr_diff(pr_number: int) -> str:
    """獲取 PR 的 diff"""
    code, out, err = run_cmd([
        "gh", "pr", "diff", str(pr_number), "--repo", GITHUB_REPO
    ])
    
    if code != 0:
        return ""
    return out

def run_cursor_review(pr_number: int, pr_title: str, diff: str, files: list[dict]) -> Optional[str]:
    """調用 Cursor CLI 做代碼審查"""
    
    # 構建審查 prompt
    prompt = f"""你是一個專業的代碼審查員。

請審查以下 GitHub PR：

## PR 標題
{pr_title}

## 變更的文件
{chr(10).join([f"- {f['filename']}: {f.get('additions', 0)} additions, {f.get('deletions', 0)} deletions" for f in files])}

## 代碼變更 (Diff)
```diff
{diff[:15000]}  # 限制長度避免超限
```

## 審查要求
請檢查以下方面：
1. **邏輯錯誤** - 是否有明顯的邏輯問題
2. **效能問題** - 是否有效能瓶頸或低效代碼
3. **安全漏洞** - 是否有安全風險（如 SQL 注入、XSS 等）
4. **錯誤處理** - 是否正確處理了錯誤情況
5. **代碼風格** - 是否符合項目規範
6. **測試覆蓋** - 是否有必要的測試

## 輸出格式
請返回 JSON 格式：
{{
    "summary": "總體評價（1-2句話）",
    "issues": [
        {{
            "severity": "critical|warning|suggestion",
            "file": "文件路徑",
            "line": "行號或範圍",
            "type": "Bug|Performance|Security|Error Handling|Style|Testing",
            "description": "問題描述",
            "suggestion": "建議修復方式"
        }}
    ],
    "praise": ["表揚點（可選）"],
    "needs_human_review": true/false
}}

請只返回 JSON，不要其他文字。
"""
    
    # 保存 prompt 到臨時文件
    prompt_file = REPO_ROOT / ".cursor_review_prompt.txt"
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)
    
    # 嘗試使用 cursor agent
    # 這個命令會在 cursor CLI 可用時生效
    cursor_available = subprocess.run(
        ["which", "cursor"],
        capture_output=True
    ).returncode == 0
    
    if cursor_available:
        print("🔍 使用 Cursor CLI 進行審查...")
        
        # 使用 cursor agent 執行審查
        code, out, err = run_cmd([
            "cursor", "agent",
            "--prompt", prompt,
            "--output", "json"
        ], timeout=600)
        
        if code == 0:
            return out
        
        print(f"⚠️ Cursor CLI 執行失敗: {err}")
        # 繼續使用其他方式
    
    # 回退方案：使用簡化的本地分析
    print("⚠️ Cursor CLI 不可用，使用本地分析...")
    return local_review(diff, files)

def local_review(diff: str, files: list[dict]) -> Optional[str]:
    """本地代碼審查（回退方案）"""
    
    issues = []
    
    for file_info in files:
        filename = file_info.get("filename", "")
        patch = file_info.get("patch", "")
        
        if not patch:
            continue
        
        lines = patch.split("\n")
        for i, line in enumerate(lines, 1):
            # 檢查常見問題
            if "console.log" in line and not filename.endswith(".test."):
                issues.append({
                    "severity": "warning",
                    "file": filename,
                    "line": f"L{i}",
                    "type": "Style",
                    "description": "發現 console.log 調用",
                    "suggestion": "生產環境應移除或使用日誌框架"
                })
            
            if "TODO" in line or "FIXME" in line:
                issues.append({
                    "severity": "suggestion",
                    "file": filename,
                    "line": f"L{i}",
                    "type": "Style",
                    "description": f"發現未完成的標記: {line.strip()[:50]}",
                    "suggestion": "確保此 TODO 在上線前完成"
                })
            
            if "except:" in line or "catch:" in line:
                # 檢查是否有空異常處理
                j = i
                while j < len(lines) and lines[j].strip() and not lines[j].startswith(("-", "+")):
                    j += 1
                
                # 簡單檢查
                if i + 2 < len(lines):
                    next_lines = " ".join(lines[i:i+3])
                    if "pass" in next_lines or "..." in next_lines:
                        issues.append({
                            "severity": "warning",
                            "file": filename,
                            "line": f"L{i}",
                            "type": "Error Handling",
                            "description": "發現空的異常處理",
                            "suggestion": "應該記錄錯誤或進行適當處理"
                        })
    
    return json.dumps({
        "summary": f"發現 {len(issues)} 個問題（本地基礎檢查）",
        "issues": issues[:20],  # 限制數量
        "praise": [],
        "needs_human_review": len(issues) > 5
    }, ensure_ascii=False)

def format_review_comment(review_data: dict, pr_title: str) -> str:
    """格式化審查結果為 PR 留言"""
    
    summary = review_data.get("summary", "無")
    issues = review_data.get("issues", [])
    praise = review_data.get("praise", [])
    needs_human = review_data.get("needs_human_review", False)
    
    comment = f"""## 🔍 代碼審查報告

### 📋 {pr_title}

**{summary}**

"""
    
    if praise:
        comment += "### ✨ 表揚\n\n"
        for p in praise[:5]:
            comment += f"- {p}\n"
        comment += "\n"
    
    if issues:
        comment += f"### 📝 發現 {len(issues)} 個問題\n\n"
        
        # 分組顯示
        critical = [i for i in issues if i.get("severity") == "critical"]
        warnings = [i for i in issues if i.get("severity") == "warning"]
        suggestions = [i for i in issues if i.get("severity") == "suggestion"]
        
        if critical:
            comment += "#### 🔴 Critical\n\n"
            for issue in critical[:5]:
                comment += f"- **{issue.get('file')}** @ {issue.get('line')}\n"
                comment += f"  - [{issue.get('type')}] {issue.get('description')}\n"
                comment += f"  - 💡 {issue.get('suggestion')}\n\n"
        
        if warnings:
            comment += "#### 🟡 Warning\n\n"
            for issue in warnings[:10]:
                comment += f"- **{issue.get('file')}** @ {issue.get('line')}\n"
                comment += f"  - [{issue.get('type')}] {issue.get('description')}\n"
                comment += f"  - 💡 {issue.get('suggestion')}\n\n"
        
        if suggestions:
            comment += "#### 🔵 Suggestion\n\n"
            for issue in suggestions[:5]:
                comment += f"- **{issue.get('file')}** @ {issue.get('line')}\n"
                comment += f"  - {issue.get('description')}\n\n"
    
    comment += "---\n"
    comment += "_由 AI DevOps (Cursor CLI) 自動審查_"
    
    if needs_human:
        comment += "\n\n⚠️ **建議人工 reviewer 進一步審查**"
    
    return comment

def post_comment(pr_number: int, body: str) -> bool:
    """在 PR 下留言"""
    code, _, err = run_cmd([
        "gh", "pr", "comment", str(pr_number),
        "--body", body,
        "--repo", GITHUB_REPO
    ])
    
    if code != 0:
        print(f"❌ 留言失敗: {err}")
        return False
    return True

def main():
    parser = argparse.ArgumentParser(description="Cursor CLI 代碼審查器")
    parser.add_argument("--pr", type=int, required=True, help="PR 號碼")
    args = parser.parse_args()
    
    print(f"🔍 Cursor CLI 代碼審查器")
    print(f"📋 PR #{args.pr}")
    
    # 獲取 PR 詳情
    pr_details = get_pr_details(args.pr)
    if not pr_details:
        print("❌ 無法獲取 PR 詳情")
        sys.exit(1)
    
    pr_title = pr_details.get("title", "")
    print(f"📌 PR: {pr_title}")
    
    # 獲取變更文件
    files = get_pr_files(args.pr)
    print(f"📁 變更文件: {len(files)} 個")
    
    # 獲取 diff
    diff = get_pr_diff(args.pr)
    print(f"📊 Diff 大小: {len(diff)} bytes")
    
    # 執行審查
    review_result = run_cursor_review(args.pr, pr_title, diff, files)
    
    if not review_result:
        print("❌ 審查失敗")
        sys.exit(1)
    
    # 解析審查結果
    try:
        review_data = json.loads(review_result)
    except json.JSONDecodeError:
        print(f"⚠️ 解析審查結果失敗，使用原始結果")
        review_data = {
            "summary": "審查完成（結果解析失敗）",
            "issues": [],
            "praise": [],
            "needs_human_review": True
        }
    
    # 格式化並發布留言
    comment = format_review_comment(review_data, pr_title)
    
    if post_comment(args.pr, comment):
        print(f"✅ 審查結果已發布到 PR #{args.pr}")
        
        # 如果需要人工審查，請求 reviewer
        if review_data.get("needs_human_review"):
            run_cmd([
                "gh", "pr", "edit", str(args.pr),
                "--repo", GITHUB_REPO,
                "--add-reviewer", "hkfish01"  # 可調整為實際的 reviewer
            ])
            print(f"👤 已請求人工審查")
    else:
        print("❌ 發布審查結果失敗")

if __name__ == "__main__":
    main()
