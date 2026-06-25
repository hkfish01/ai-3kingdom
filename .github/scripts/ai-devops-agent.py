#!/usr/bin/env python3
"""
AI DevOps Agent - 自動分析系統狀態並生成改進代碼
"""
import os
import json
import re
import subprocess
import urllib.request
import urllib.error
from datetime import datetime

REPO_ROOT = os.environ.get('GITHUB_WORKSPACE', os.getcwd())
KIMI_API_KEY = os.environ.get('KIMI_API_KEY', '')
GITHUB_REPO = os.environ.get('GITHUB_REPOSITORY', '')

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
    except:
        return None

def main():
    # Read system status
    code, recent_commits, _ = run_cmd("git log --oneline -10")
    code, git_status, _ = run_cmd("git status --porcelain")
    
    nl = "\n"
    context = f"""Current system status:
- Uncommitted changes: {len([l for l in git_status.strip().split(nl) if l])} files
- Latest commit: {recent_commits.strip().split(nl)[0] if recent_commits.strip() else 'N/A'}

Recent 5 commits:
{recent_commits.strip()}"""

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

    # Read files to modify
    context_files = {}
    for file_path in decision.get("files_to_modify", [])[:3]:
        full_path = os.path.join(REPO_ROOT, file_path)
        if os.path.exists(full_path):
            with open(full_path, 'r') as f:
                content = f.read()[:3000]
                context_files[file_path] = content
                print(f"Reading: {file_path}")

    context_str = "\n\n".join([f"=== {p} ===\n{c}" for p, c in context_files.items()])

    # Generate code
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

    # Create branch
    branch_name = f"ai-devops/{task_name.lower().replace(' ', '-').replace('_', '-')}"
    print(f"Creating branch: {branch_name}")
    
    run_cmd("git checkout -b " + branch_name)

    # Apply changes
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

    # Commit
    run_cmd("git add -A")
    commit_msg = code_data.get("commit_message", f"feat: {task_name}")
    run_cmd(f'git commit -m "{commit_msg}"')
    
    # Push
    run_cmd(f"git push -u origin {branch_name}")
    print("Branch pushed")

    # Create PR
    pr_body = f"""## AI DevOps Auto-generated

### Task: {task_name}
### Reason: {decision.get('reason', '')}

**Summary:** {code_data.get('summary', '')}

---
_Auto-generated by AI DevOps Agent (Kimi K2.7)_"""

    code, pr_out, _ = run_cmd(f'gh pr create --title "AI: {task_name}" --body "{pr_body.replace(nl, chr(92)+"n")}" --base main')
    
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

    # Save output
    with open(os.environ.get('GITHUB_ENV', '/tmp/github_env'), 'a') as f:
        f.write(f"branch_name={branch_name}\n")
        f.write(f"task_name={task_name}\n")
        f.write(f"pr_number={pr_number or 0}\n")
        f.write(f"summary={code_data.get('summary', '')}\n")

    return {
        "execute": True,
        "pr_number": pr_number,
        "task_name": task_name
    }

if __name__ == "__main__":
    main()
