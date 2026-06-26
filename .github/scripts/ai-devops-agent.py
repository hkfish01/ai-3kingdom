#!/usr/bin/env python3
"""
AI DevOps Agent - 自動分析系統狀態並生成改進代碼
支援模式：
- generate：分析系統、生成改進、建立 PR
- review：檢查候選 PR、決定是否批准
"""
import os
import sys
import json
import re
import subprocess
import argparse
import urllib.request
import urllib.error

REPO_ROOT = os.environ.get('GITHUB_WORKSPACE', os.getcwd())
KIMI_API_KEY = os.environ.get('KIMI_API_KEY', '')
GITHUB_REPO = os.environ.get('GITHUB_REPOSITORY', '')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')


def run_cmd(cmd, cwd=REPO_ROOT):
    result = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def http_request(endpoint, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {KIMI_API_KEY}"
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"HTTP Error: {e}")
        return None


def call_kimi(prompt, system_prompt=""):
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

    response = http_request("https://api.moonshot.cn/v1/chat/completions", payload)
    if response and "choices" in response:
        return response["choices"][0]["message"]["content"]
    return None


def parse_json_response(response):
    """Parse JSON from AI response"""
    if not response:
        return None
    try:
        json_match = re.search(r'```json\s*(.+?)\s*```', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        return json.loads(response)
    except Exception:
        return None


def get_open_ai_prs():
    code, out, _ = run_cmd("gh pr list --state open --json number,title,labels,author,updatedAt,headRefName,mergeable,statusCheckRollup")
    if code != 0:
        return []
    prs = json.loads(out or '[]')
    results = []
    for pr in prs:
        labels = [l.get('name') for l in pr.get('labels', [])]
        if 'ai-devops' in labels:
            results.append({
                'number': pr['number'],
                'title': pr['title'],
                'head': pr.get('headRefName', ''),
                'updatedAt': pr.get('updatedAt', ''),
                'mergeable': pr.get('mergeable'),
                'checks': pr.get('statusCheckRollup', []),
            })
    return results


def approve_pr(pr_number: int, reason: str):
    run_cmd(f"gh pr edit {pr_number} --add-label approved")
    run_cmd(f"gh pr comment {pr_number} --body '✅ AI DevOps 已審核通過\\n\\n原因：{reason}'")


def reject_pr(pr_number: int, reason: str):
    run_cmd(f"gh pr edit {pr_number} --add-label rejected")
    run_cmd(f"gh pr comment {pr_number} --body '❌ AI DevOps 審核未通過\\n\\n原因：{reason}'")


def mode_generate():
    code, recent_commits, _ = run_cmd("git log --oneline -10")
    code, git_status, _ = run_cmd("git status --porcelain")

    code, issues_out, _ = run_cmd("gh issue list --state open --json number --jq 'length'")
    open_issues = int(issues_out.strip() or 0)

    nl = "\n"
    context = f"""Current system status:
- Uncommitted changes: {len([l for l in git_status.strip().split(nl) if l])} files
- Latest commit: {recent_commits.strip().split(nl)[0] if recent_commits.strip() else 'N/A'}
- Open issues: {open_issues}

Recent 5 commits:
{recent_commits.strip()}"""

    print(f"System status: {len([l for l in git_status.strip().split(nl) if l])} uncommitted, {open_issues} open issues")
    print("AI analyzing system...")
    response = call_kimi(context)

    if not response:
        print("Kimi API call failed")
        return {"execute": False}

    decision = parse_json_response(response)
    if not decision:
        print("Failed to parse decision")
        return {"execute": False}

    if not decision.get("execute", False):
        print("AI decision: No action needed")
        return {"execute": False}

    task_name = decision["task_name"]
    print(f"Task: {task_name}")
    print(f"Reason: {decision.get('reason', '')}")

    context_files = {}
    for file_path in decision.get("files_to_modify", [])[:3]:
        full_path = os.path.join(REPO_ROOT, file_path)
        if os.path.exists(full_path):
            with open(full_path, 'r') as f:
                content = f.read()[:3000]
                context_files[file_path] = content
                print(f"Reading: {file_path}")

    context_str = "\n\n".join([f"=== {p} ===\n{c}" for p, c in context_files.items()])

    code_prompt = f"""Task: {task_name}
Description: {decision['description']}

Existing code:
{context_str if context_str else 'No existing code (new feature)'}

Generate code changes, return JSON:
{{
    "files": [
        {{
            "file_path": "path/filename",
            "action": "create/modify/delete",
            "content": "full file content"
        }}
    ],
    "commit_message": "commit message",
    "summary": "change summary"
}}"""

    print("AI generating code...")
    code_response = call_kimi(code_prompt)

    if not code_response:
        print("Code generation failed")
        return {"execute": False}

    code_data = parse_json_response(code_response)
    if not code_data:
        print("Failed to parse code")
        return {"execute": False}

    branch_name = f"ai-devops/{task_name.lower().replace(' ', '-').replace('_', '-')}"
    print(f"Creating branch: {branch_name}")

    run_cmd("git checkout -b " + branch_name)

    for file_change in code_data.get("files", []):
        file_path = os.path.join(REPO_ROOT, file_change["file_path"])
        action = file_change.get("action", "modify")

        if action == "delete":
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Deleting: {file_change['file_path']}")
        else:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w') as f:
                f.write(file_change.get("content", ""))
            print(f"Creating/updating: {file_change['file_path']}")

    run_cmd("git add -A")
    commit_msg = code_data.get("commit_message", f"feat: {task_name}")
    run_cmd(f'git commit -m "{commit_msg}"')

    run_cmd(f"git push -u origin {branch_name}")
    print("Branch pushed")

    pr_body = f"""## AI DevOps Auto-generated

### Task: {task_name}
### Reason: {decision.get('reason', '')}

**Summary:** {code_data.get('summary', '')}

---
_Auto-generated by AI DevOps Agent (Kimi K2.7)_"""

    code, pr_out, _ = run_cmd(f'gh pr create --title "AI: {task_name}" --body "{pr_body.replace(chr(10), chr(92)+"n")}" --base main --label ai-devops')

    pr_number = None
    if code == 0:
        pr_match = re.search(r'pull/(\d+)', pr_out)
        if pr_match:
            pr_number = int(pr_match.group(1))

    if not pr_number:
        code, out, _ = run_cmd(f'gh pr list --head {branch_name} --json number --jq ".[0].number"')
        if code == 0 and out.strip():
            pr_number = int(out.strip())

    print(f"PR #{pr_number} created" if pr_number else "PR creation failed")

    with open(os.environ.get('GITHUB_OUTPUT', '/tmp/github_output'), 'a') as f:
        f.write(f"branch_name={branch_name}\n")
        f.write(f"task_name={task_name}\n")
        f.write(f"pr_number={pr_number or 0}\n")
        f.write(f"summary={code_data.get('summary', '')}\n")

    with open(os.environ.get('GITHUB_ENV', '/tmp/github_env'), 'a') as f:
        f.write(f"branch_name={branch_name}\n")
        f.write(f"task_name={task_name}\n")
        f.write(f"pr_number={pr_number or 0}\n")
        f.write(f"summary={code_data.get('summary', '')}\n")

    print(f"OUTPUT: branch_name={branch_name}")
    print(f"OUTPUT: task_name={task_name}")
    print(f"OUTPUT: pr_number={pr_number or 0}")
    print(f"OUTPUT: summary={code_data.get('summary', '')}")

    return {
        "execute": True,
        "pr_number": pr_number,
        "task_name": task_name
    }


def mode_review(prs_file=None):
    prs = get_open_ai_prs() if prs_file is None else json.loads(open(prs_file, 'r', encoding='utf-8').read() or '[]')
    if not prs:
        print('No AI DevOps PRs found for review')
        approve = False
        approved_pr_number = 0
        reason = '沒有候選 PR'
    else:
        summary_lines = []
        for pr in prs:
            checks = []
            for check in pr.get('checks', []):
                name = check.get('name', 'check')
                conclusion = check.get('conclusion', '')
                if conclusion:
                    checks.append(f"{name}: {conclusion}")
            summary_lines.append(f"#{pr['number']} {pr['title']} | mergeable={pr.get('mergeable')} | checks={', '.join(checks) if checks else 'n/a'}")

        review_prompt = f"""你是 AI DevOps 的程式碼審核員。請根據以下候選 PR 決定是否批准合併與部署。

候選 PR：
{chr(10).join(summary_lines)}

規則：
1. 只批准 mergeable=true 且 CI 全綠的 PR
2. 如果沒有候選 PR，回傳 approve=false
3. 如果有多個候選 PR，優先批准最新更新的
4. 回傳 JSON：
{{ "approve": true/false, "approved_pr_number": 123, "reason": "原因" }}"""

        response = call_kimi(review_prompt)
        decision = parse_json_response(response) or {}
        approve = bool(decision.get('approve', False))
        approved_pr_number = int(decision.get('approved_pr_number') or 0)
        reason = decision.get('reason') or ('沒有可批准的 PR' if not approve else '符合 CI/mergeable 條件')

        if approve and approved_pr_number:
            approve_pr(approved_pr_number, reason)
        elif prs:
            reject_pr(prs[0]['number'], reason)

    result = {
        'approve': approve,
        'approved_pr_number': approved_pr_number,
        'reason': reason,
        'reviewed_count': len(prs)
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    out_path = os.environ.get('GITHUB_OUTPUT', '/tmp/github_output')
    with open(out_path, 'a', encoding='utf-8') as f:
        f.write(f"approve={str(approve).lower()}\n")
        f.write(f"approved_pr_number={approved_pr_number}\n")

    out_env = os.environ.get('GITHUB_ENV', '/tmp/github_env')
    with open(out_env, 'a', encoding='utf-8') as f:
        f.write(f"APPROVE={str(approve).lower()}\n")
        f.write(f"APPROVED_PR_NUMBER={approved_pr_number}\n")

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', default='generate')
    parser.add_argument('--prs-file')
    parser.add_argument('--output-file')
    args = parser.parse_args()

    if args.mode == 'review':
        result = mode_review(args.prs_file)
    else:
        result = mode_generate()

    if args.output_file:
        with open(args.output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
