#!/usr/bin/env python3
"""
AI DevOps 自主代理 - 完全自動化管理系統

功能：
1. 檢查用戶情況和系統狀態
2. 使用 Kimi K2.7 進行開發新功能及修改
3. 自行提交 PR 及部署
4. 完成部署後發送系統公告
"""

import os
import sys
import json
import re
import subprocess
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
GITHUB_REPO = "hkfish01/ai-3kingdom"
KIMI_API_KEY = os.environ.get("KIMI_API_KEY", "")
OBSIDIAN_VAULT = Path(os.environ.get(
    "OBSIDIAN_VAULT",
    "/Volumes/1.5T/AI-DATA/AI-Knowledge-Vault/01-projects/ai-3kingdom"
))

def run_cmd(cmd, cwd=REPO_ROOT, timeout=60):
    """執行 shell 命令"""
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timeout"
    except Exception as e:
        return -1, "", str(e)

def check_gh_auth():
    """檢查 GitHub CLI 認證狀態"""
    code, out, _ = run_cmd(["gh", "auth", "status"])
    return code == 0

def http_request(endpoint, payload):
    """發送 HTTP 請求到 Kimi API"""
    import urllib.request, urllib.error
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {KIMI_API_KEY}"
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        print(f"  ❌ HTTP 錯誤 {e.code}: {error_body}")
        return None
    except Exception as e:
        print(f"  ❌ 請求失敗: {e}")
        return None

def call_kimi(prompt: str, system_prompt: str = "") -> Optional[str]:
    """調用 Kimi K2.7 API"""
    if not KIMI_API_KEY:
        print("  ❌ KIMI_API_KEY 未設定")
        return None
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": "kimi-k2.7-code",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 8192
    }
    
    response = http_request(
        "https://api.moonshot.cn/v1/chat/completions",
        payload
    )
    
    if response and "choices" in response:
        return response["choices"][0]["message"]["content"]
    return None

def get_system_status() -> Dict:
    """獲取系統狀態"""
    print("\n📊 檢查系統狀態...")
    status = {
        "git_status": {},
        "open_issues": [],
        "recent_commits": [],
        "prs": []
    }
    
    # Git 狀態
    code, out, _ = run_cmd(["git", "status", "--porcelain"])
    status["git_status"]["has_changes"] = bool(out.strip())
    status["git_status"]["changes"] = out.strip().split("\n") if out.strip() else []
    
    # 最新 commits
    code, out, _ = run_cmd(["git", "log", "--oneline", "-10"])
    status["recent_commits"] = out.strip().split("\n") if out.strip() else []
    
    # Open Issues
    code, out, _ = run_cmd([
        "gh", "issue", "list", "--repo", GITHUB_REPO, 
        "--state", "open", "--json", "number,title,labels"
    ])
    if code == 0 and out.strip():
        try:
            status["open_issues"] = json.loads(out)
        except:
            pass
    
    # Open PRs
    code, out, _ = run_cmd([
        "gh", "pr", "list", "--repo", GITHUB_REPO,
        "--state", "open", "--json", "number,title,body"
    ])
    if code == 0 and out.strip():
        try:
            status["prs"] = json.loads(out)
        except:
            pass
    
    return status

def analyze_and_plan(status: Dict) -> List[Dict]:
    """分析系統狀態並制定計劃"""
    print("\n🧠 分析系統並制定開發計劃...")
    
    system_context = f"""
當前系統狀態：
- 未提交的變更: {len(status['git_status'].get('changes', []))} 個文件
- Open Issues: {len(status['open_issues'])} 個
- Open PRs: {len(status['prs'])} 個
- 最新 Commit: {status['recent_commits'][0] if status['recent_commits'] else 'N/A'}

最近 5 個 Commit：
{chr(10).join(status['recent_commits'][:5]) if status['recent_commits'] else '無'}
"""
    
    prompt = f"""{system_context}

作為 AI DevOps 代理，你需要分析上述狀態並制定工作計劃。

考慮因素：
1. 是否有未提交的代碼需要處理？
2. 是否有緊急的 issues 需要解決？
3. 如何改進系統功能和代碼質量？

請生成 1-3 個具體的開發任務，每個任務包含：
- 任務名稱（英文）
- 任務描述（中文）
- 優先級（high/medium/low）
- 預計修改的文件

返回 JSON 格式：
{{
    "tasks": [
        {{
            "name": "task-name",
            "description": "任務描述",
            "priority": "high/medium/low",
            "files_to_modify": ["file1.py", "file2.ts"],
            "new_files": ["new_feature.py"]
        }}
    ],
    "summary": "整體計劃摘要"
}}

只返回 JSON，不要其他文字。
"""
    
    response = call_kimi(prompt)
    if not response:
        return []
    
    try:
        json_match = re.search(r'```json\s*(.+?)\s*```', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(1))
        else:
            data = json.loads(response)
        return data.get("tasks", [])
    except json.JSONDecodeError as e:
        print(f"  ⚠️ 解析計劃失敗: {e}")
        return []

def develop_feature(task: Dict) -> Optional[Dict]:
    """使用 Kimi K2.7 開發功能"""
    print(f"\n🔧 開發功能: {task['name']}")
    print(f"   描述: {task['description']}")
    
    # 讀取相關文件以獲取上下文
    context_files = {}
    for file_path in task.get("files_to_modify", []):
        full_path = REPO_ROOT / file_path
        if full_path.exists():
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    context_files[file_path] = f.read()[:5000]  # 限制大小
            except:
                pass
    
    context_str = ""
    for path, content in context_files.items():
        context_str += f"\n\n=== {path} ===\n{content}"
    
    prompt = f"""任務：{task['name']}
描述：{task['description']}

現有代碼上下文：
{context_str if context_str else '無現有代碼（新建功能）'}

項目結構：
- backend/ - FastAPI 後端
- frontend/ - Next.js 前端
- scripts/ - 工具腳本

請根據任務描述，生成代碼變更：

返回 JSON 格式：
{{
    "files": [
        {{
            "file_path": "路徑/文件名",
            "action": "create/modify/delete",
            "content": "完整文件內容（如果是新建或修改）"
        }}
    ],
    "commit_message": "簡潔的 commit 訊息",
    "summary": "變更摘要"
}}

只返回 JSON，不要其他文字。"""
    
    response = call_kimi(prompt)
    if not response:
        return None
    
    try:
        json_match = re.search(r'```json\s*(.+?)\s*```', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(1))
        else:
            data = json.loads(response)
        return data
    except json.JSONDecodeError as e:
        print(f"  ❌ 解析代碼失敗: {e}")
        return None

def create_branch_and_commit(code_data: Dict, task_name: str) -> Optional[str]:
    """創建 branch 並提交代碼"""
    branch_name = f"ai-devops/{task_name.lower().replace(' ', '-').replace('_', '-')}"
    
    # 創建/切換 branch
    run_cmd(["git", "fetch", "origin"])
    run_cmd(["git", "checkout", "main"])
    run_cmd(["git", "pull", "origin", "main"])
    
    code, _, _ = run_cmd(["git", "checkout", "-b", branch_name])
    if code != 0:
        print(f"  ❌ 創建 branch 失敗")
        return None
    
    # 應用代碼變更
    files = code_data.get("files", [])
    for file_change in files:
        file_path = REPO_ROOT / file_change["file_path"]
        action = file_change.get("action", "modify")
        
        if action == "delete":
            if file_path.exists():
                file_path.unlink()
                print(f"  🗑️ 刪除: {file_change['file_path']}")
        else:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(file_change.get("content", ""))
                print(f"  ✅ {'創建' if action == 'create' else '更新'}: {file_change['file_path']}")
            except Exception as e:
                print(f"  ❌ 寫入失敗 {file_change['file_path']}: {e}")
                run_cmd(["git", "checkout", "main"])
                run_cmd(["git", "branch", "-D", branch_name])
                return None
    
    # 提交
    run_cmd(["git", "add", "-A"])
    commit_msg = code_data.get("commit_message", f"feat: {task_name}")
    code, _, err = run_cmd(["git", "commit", "-m", commit_msg])
    if code != 0:
        print(f"  ❌ 提交失敗: {err}")
        return None
    
    # 推送
    code, _, err = run_cmd(["git", "push", "-u", "origin", branch_name])
    if code != 0:
        print(f"  ❌ 推送失敗: {err}")
        return None
    
    return branch_name

def create_pr(branch_name: str, task_name: str, description: str) -> Optional[int]:
    """創建 Pull Request"""
    body = f"""## 🤖 AI DevOps 自動生成

### 任務：{task_name}

{description}

---

_由 AI DevOps Agent (Kimi K2.7) 自動開發_

**部署後將自動發送系統公告。**"""

    code, out, err = run_cmd([
        "gh", "pr", "create", "--repo", GITHUB_REPO,
        "--title", f"🤖 {task_name}",
        "--body", body,
        "--base", "main"
    ])
    
    if code != 0:
        print(f"  ❌ 創建 PR 失敗: {err}")
        return None
    
    # 提取 PR 號碼
    pr_match = re.search(r'pull/(\d+)', out)
    if pr_match:
        return int(pr_match.group(1))
    
    # 嘗試從 URL 提取
    code, out, _ = run_cmd([
        "gh", "pr", "list", "--repo", GITHUB_REPO,
        "--head", branch_name, "--json", "number"
    ])
    if code == 0 and out.strip():
        try:
            data = json.loads(out)
            if data:
                return data[0]["number"]
        except:
            pass
    
    return None

def merge_pr(pr_number: int) -> bool:
    """合併 Pull Request"""
    print(f"\n🔀 合併 PR #{pr_number}...")
    
    # 添加 ai-devops 標籤
    run_cmd(["gh", "pr", "edit", str(pr_number), "--add-label", "ai-devops"])
    
    # 合併 PR
    code, _, err = run_cmd([
        "gh", "pr", "merge", str(pr_number),
        "--squash", "--delete-branch"
    ])
    
    if code != 0:
        print(f"  ⚠️ 合併失敗: {err}")
        # 嘗試使用其他方式合併
        code, _, err = run_cmd([
            "gh", "pr", "merge", str(pr_number),
            "--squash", "-m", f"Merge PR #{pr_number}"
        ])
        if code != 0:
            print(f"  ❌ 合併失敗: {err}")
            return False
    
    print(f"  ✅ PR #{pr_number} 已合併")
    return True

def trigger_deploy() -> bool:
    """觸發 GitHub Actions 部署"""
    print("\n🚀 觸發部署...")
    
    code, out, err = run_cmd([
        "gh", "workflow", "run", "Deploy to Production",
        "--repo", GITHUB_REPO,
        "--field", "skip_backup=false"
    ])
    
    if code != 0:
        print(f"  ⚠️ 觸發部署失敗: {err}")
        return False
    
    print(f"  ✅ 部署已觸發")
    
    # 等待部署完成（最多 20 分鐘）
    print("  ⏳ 等待部署完成...")
    for i in range(40):  # 40 * 30s = 20 分鐘
        import time
        time.sleep(30)
        
        code, out, _ = run_cmd([
            "gh", "run", "list", "--repo", GITHUB_REPO,
            "--workflow", "Deploy to Production",
            "--limit", "1", "--json", "status,conclusion"
        ])
        
        if code == 0 and out.strip():
            try:
                runs = json.loads(out)
                if runs:
                    status = runs[0]["status"]
                    conclusion = runs[0].get("conclusion", "")
                    
                    if status == "completed":
                        if conclusion == "success":
                            print(f"  ✅ 部署成功！")
                            return True
                        else:
                            print(f"  ❌ 部署失敗: {conclusion}")
                            return False
                    else:
                        print(f"  進度: {status}... ({i+1}/40)")
            except:
                pass
    
    print("  ⚠️ 部署超時")
    return False

def post_announcement(task_name: str, description: str) -> bool:
    """在系統內發布公告"""
    print("\n📢 發布系統公告...")
    
    # 構建公告內容
    announcement = {
        "title": f"🤖 AI DevOps 更新：{task_name}",
        "content": f"""
## 系統更新公告

**更新內容：** {description}

**發布時間：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**狀態：** ✅ 已成功部署

---

_此公告由 AI DevOps Agent 自動發布_
""",
        "type": "system_update",
        "priority": "normal"
    }
    
    # 嘗試通過 API 或直接寫入數據庫發布公告
    # 這裡使用 curl 調用本地 API
    
    api_url = os.environ.get("CITY_BASE_URL", "http://localhost:10090")
    api_key = os.environ.get("ADMIN_API_KEY", "")
    
    if not api_key:
        print("  ⚠️ ADMIN_API_KEY 未設定，跳過公告")
        return False
    
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{api_url}/api/admin/announcements",
            data=json.dumps(announcement).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status == 200 or response.status == 201:
                print("  ✅ 公告已發布")
                return True
    except Exception as e:
        print(f"  ⚠️ 發布公告失敗: {e}")
    
    return False

def post_github_comment(pr_number: int, message: str):
    """在 GitHub PR 發布評論"""
    code, _, _ = run_cmd([
        "gh", "pr", "comment", str(pr_number),
        "--body", message
    ])


def write_obsidian_daily_report(report: Dict):
    """寫入每日報告到 Obsidian"""
    if not OBSIDIAN_VAULT.exists():
        print("  ⚠️ Obsidian vault 不存在，跳過寫入")
        return

    daily_dir = OBSIDIAN_VAULT / "00-daily"
    daily_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = daily_dir / f"{date_str}.md"

    # 構建每日報告內容
    content = f"""# AI DevOps 每日報告 — {date_str}

> 自動生成 by AI DevOps Agent

## 執行摘要

- **執行時間：** {report.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M"))}
- **成功任務：** {report.get("completed_count", 0)}/{report.get("total_count", 0)}

"""

    tasks = report.get("tasks", [])
    if tasks:
        content += "## 已完成任務\n\n"
        for task in tasks:
            status_emoji = "✅" if task.get("status") == "success" else "❌"
            content += f"- {status_emoji} **{task.get('name', 'N/A')}**\n"
            if task.get("pr"):
                content += f"  - PR: #{task['pr']}\n"
            if task.get("summary"):
                content += f"  - {task['summary']}\n"
    else:
        content += "## 任務狀態\n\n- 沒有需要處理的任務\n"

    content += f"""
## 系統狀態

- 未提交變更：{report.get("git_changes", 0)} 個文件
- Open Issues：{report.get("open_issues", 0)} 個
- Open PRs：{report.get("open_prs", 0)} 個

---

_由 AI DevOps Agent 自動記錄_
"""

    try:
        filename.write_text(content, encoding="utf-8")
        print(f"  📓 已寫入每日報告到 Obsidian: {filename.name}")
    except Exception as e:
        print(f"  ⚠️ 寫入 Obsidian 失敗: {e}")


def write_obsidian_optimization(suggestion: Dict):
    """寫入優化建議到 Obsidian"""
    if not OBSIDIAN_VAULT.exists():
        return

    opt_dir = OBSIDIAN_VAULT / "03-optimization"
    opt_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = suggestion.get("name", "untitled").lower().replace(" ", "-").replace("_", "-")
    filename = opt_dir / f"{date_str}—{slug}.md"

    content = f"""# {suggestion.get("name", "優化建議")}

> 生成時間：{datetime.now().strftime("%Y-%m-%d %H:%M")}

## 類型
- 類別：{suggestion.get("category", "general")}
- 優先級：{suggestion.get("priority", "medium")}

## 建議內容
{suggestion.get("description", "無描述")}

## 預期影響
{suggestion.get("impact", "待評估")}

## 關聯檔案
"""
    for f in suggestion.get("files", []):
        content += f"- `ai-3kingdom/{f}`\n"

    content += """
## 狀態
- [ ] 待評估
- [ ] 已採納
- [ ] 已拒絕

---

_由 AI DevOps Agent 自動記錄_
"""

    try:
        filename.write_text(content, encoding="utf-8")
        print(f"  📓 已寫入優化建議: {filename.name}")
    except Exception as e:
        print(f"  ⚠️ 寫入失敗: {e}")

def main():
    print("=" * 60)
    print("🤖 AI DevOps 自主代理")
    print("=" * 60)
    
    if not check_gh_auth():
        print("❌ GitHub CLI 未登入，請先執行: gh auth login")
        sys.exit(1)
    
    if not KIMI_API_KEY:
        print("❌ KIMI_API_KEY 環境變量未設定")
        sys.exit(1)
    
    print(f"\n📁 Repo: {REPO_ROOT}")
    print(f"🌐 GitHub: {GITHUB_REPO}")
    
    # ====== 步驟 1: 檢查系統狀態 ======
    status = get_system_status()
    print(f"\n📊 系統狀態:")
    print(f"   - 未提交變更: {len(status['git_status'].get('changes', []))} 個")
    print(f"   - Open Issues: {len(status['open_issues'])} 個")
    print(f"   - Open PRs: {len(status['prs'])} 個")
    
    # ====== 步驟 2: 分析並制定計劃 ======
    tasks = analyze_and_plan(status)
    if not tasks:
        print("\n✅ 沒有需要處理的任務")
        sys.exit(0)
    
    print(f"\n📋 制定 {len(tasks)} 個開發任務")
    
    # ====== 步驟 3: 執行每個任務 ======
    completed_tasks = []
    for i, task in enumerate(tasks):
        print(f"\n{'='*60}")
        print(f"任務 {i+1}/{len(tasks)}: {task['name']}")
        print(f"{'='*60}")
        
        # 3.1 使用 Kimi K2.7 開發
        code_data = develop_feature(task)
        if not code_data:
            print(f"  ❌ 任務開發失敗")
            continue
        
        # 3.2 創建 branch 並提交
        branch_name = create_branch_and_commit(code_data, task["name"])
        if not branch_name:
            print(f"  ❌ 分支提交失敗")
            continue
        
        # 3.3 創建 PR
        pr_number = create_pr(
            branch_name,
            task["name"],
            code_data.get("summary", task["description"])
        )
        if not pr_number:
            print(f"  ❌ PR 創建失敗")
            continue
        
        print(f"  ✅ PR #{pr_number} 已創建")
        
        # 3.4 合併 PR
        if not merge_pr(pr_number):
            continue
        
        # 3.5 觸發部署
        if not trigger_deploy():
            post_github_comment(pr_number, "⚠️ 部署失敗，請手動檢查")
            continue
        
        # 3.6 發布公告
        post_announcement(task["name"], code_data.get("summary", task["description"]))
        
        completed_tasks.append({
            "task": task["name"],
            "pr": pr_number,
            "status": "✅ 成功"
        })
    
    # ====== 完成總結 ======
    print(f"\n{'='*60}")
    print("📊 AI DevOps 執行完成")
    print(f"{'='*60}")
    
    if completed_tasks:
        print(f"\n✅ 成功完成 {len(completed_tasks)}/{len(tasks)} 個任務：")
        for item in completed_tasks:
            print(f"   - {item['task']} (PR #{item['pr']})")
    else:
        print("\n❌ 沒有任務成功完成")
    
    # ====== 寫入 Obsidian ======
    daily_report = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_count": len(tasks),
        "completed_count": len(completed_tasks),
        "tasks": completed_tasks,
        "git_changes": len(status["git_status"].get("changes", [])),
        "open_issues": len(status["open_issues"]),
        "open_prs": len(status["prs"]),
    }
    write_obsidian_daily_report(daily_report)
    
    # 發布總結評論
    if completed_tasks:
        summary = "## 🤖 AI DevOps 執行報告\n\n"
        summary += f"**執行時間：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        summary += "### 已完成的任務\n\n"
        for item in completed_tasks:
            summary += f"- ✅ {item['task']}\n"
        
        # 在最新的 PR 發布總結
        if completed_tasks:
            post_github_comment(completed_tasks[-1]["pr"], summary)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="僅分析不執行")
    args = parser.parse_args()
    
    if args.dry_run:
        status = get_system_status()
        tasks = analyze_and_plan(status)
        print(json.dumps({"status": status, "tasks": tasks}, indent=2, ensure_ascii=False))
    else:
        main()
