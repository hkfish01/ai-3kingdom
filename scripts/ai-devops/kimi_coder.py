#!/usr/bin/env python3
"""
Kimi K2.7 代碼生成器
- 解析 PR 描述中的 planned_features
- 調用 Kimi K2.7 API 生成代碼
- 創建 branch 和 PR
"""

import os
import sys
import json
import re
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

# ============ 配置 ============
KIMI_ENDPOINT = "https://api.kimi.com/coding/v1"
MODEL = "kimi-k2.7-code"
API_KEY = "sk-kimi-gc2tvUfDoX1T60O8Y6E32Oo2V3rbx2RCTyFMdZLTr0j2qebKIJ8wg2oJtRpNYCVY"

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
GITHUB_REPO = "hkfish01/ai-3kingdom"

# ============ 工具函數 ============

def run_cmd(cmd: list[str], cwd: Path = REPO_ROOT) -> tuple[int, str, str]:
    """執行 shell 命令"""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True
    )
    return result.returncode, result.stdout, result.stderr

def http_request(endpoint: str, api_key: str, payload: dict) -> Optional[dict]:
    """發送 HTTP 請求到 Kimi API"""
    import urllib.request
    import urllib.error
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        print(f"❌ HTTP 錯誤 {e.code}: {error_body}")
        return None
    except Exception as e:
        print(f"❌ 請求失敗: {e}")
        return None

def parse_planned_features(pr_body: str) -> list[dict]:
    """解析 PR 描述中的 planned_features"""
    features = []
    
    # 嘗試解析 JSON 格式
    json_match = re.search(r'```json\s*({\s*"planned_features".*?})\s*```', pr_body, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            features = data.get("planned_features", [])
        except json.JSONDecodeError:
            pass
    
    # 嘗試解析 Markdown 格式
    if not features:
        feature_pattern = re.compile(
            r'(?:^|\n)##?\s*Feature\s+(\d+)[:\s]*(.+?)(?=\n##|\Z)',
            re.IGNORECASE | re.DOTALL
        )
        for match in feature_pattern.finditer(pr_body):
            feature_id = match.group(1).strip()
            content = match.group(2).strip()
            
            # 提取名稱
            name_match = re.search(r'Name[:\s*]*(.+?)(?:\n|$)', content)
            name = name_match.group(1).strip() if name_match else f"feature-{feature_id}"
            
            # 提取描述
            desc_match = re.search(r'Description[:\s*]*(.+?)(?:\n\n|\Z)', content, re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else ""
            
            # 提取代碼模板
            code_blocks = re.findall(r'```[\w]*\s*(.+?)```', content, re.DOTALL)
            code_template = "\n\n".join(code_blocks)
            
            features.append({
                "id": feature_id,
                "name": name,
                "description": description,
                "code_template": code_template
            })
    
    return features

def call_kimi(prompt: str) -> Optional[str]:
    """調用 Kimi K2.7 生成代碼"""
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3,
        "max_tokens": 8192
    }
    
    response = http_request(f"{KIMI_ENDPOINT}/chat/completions", API_KEY, payload)
    
    if response and "choices" in response:
        return response["choices"][0]["message"]["content"]
    return None

def create_branch(feature_name: str) -> Optional[str]:
    """創建 Git branch"""
    branch_name = f"feat/{feature_name.lower().replace(' ', '-').replace('_', '-')}"
    
    # 確保從 main branch 更新
    run_cmd(["git", "fetch", "origin"])
    run_cmd(["git", "checkout", "main"])
    run_cmd(["git", "pull", "origin", "main"])
    
    # 創建並切換 branch
    code, out, err = run_cmd(["git", "checkout", "-b", branch_name])
    
    if code != 0:
        print(f"❌ 創建 branch 失敗: {err}")
        return None
    
    return branch_name

def apply_code_changes(code_changes: list[dict]) -> bool:
    """應用代碼變更"""
    for change in code_changes:
        file_path = REPO_ROOT / change.get("file_path", "")
        content = change.get("content", "")
        
        # 確保目錄存在
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 寫入文件
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  ✅ 創建/更新: {change.get('file_path')}")
        except Exception as e:
            print(f"  ❌ 寫入失敗 {change.get('file_path')}: {e}")
            return False
    
    return True

def commit_and_push(branch_name: str, feature_name: str) -> bool:
    """提交並推送代碼"""
    # 添加所有變更
    run_cmd(["git", "add", "-A"])
    
    # 檢查是否有變更
    code, out, _ = run_cmd(["git", "status", "--porcelain"])
    if not out.strip():
        print("  ⚠️ 沒有代碼變更")
        return False
    
    # 提交
    commit_msg = f"feat: {feature_name}\n\nGenerated by AI DevOps"
    code, _, err = run_cmd(["git", "commit", "-m", commit_msg])
    
    if code != 0:
        print(f"❌ 提交失敗: {err}")
        return False
    
    # 推送
    code, _, err = run_cmd(["git", "push", "-u", "origin", branch_name])
    
    if code != 0:
        print(f"❌ 推送失敗: {err}")
        return False
    
    return True

def create_pr(branch_name: str, feature_name: str, description: str) -> Optional[int]:
    """創建 GitHub PR"""
    title = f"feat: {feature_name}"
    body = f"""## {feature_name}

{description}

_Generated by AI DevOps (Kimi K2.7)_"""

    code, out, err = run_cmd([
        "gh", "pr", "create",
        "--repo", GITHUB_REPO,
        "--title", title,
        "--body", body,
        "--base", "main"
    ])
    
    if code != 0:
        print(f"❌ 創建 PR 失敗: {err}")
        return None
    
    # 提取 PR 號碼
    pr_match = re.search(r'https://github\.com/.*?/pull/(\d+)', out)
    if pr_match:
        return int(pr_match.group(1))
    
    return None

def main():
    parser = argparse.ArgumentParser(description="Kimi K2.7 代碼生成器")
    parser.add_argument("--pr", type=int, required=True, help="觸發的 PR 號碼")
    parser.add_argument("--body", type=str, default="", help="PR 描述")
    args = parser.parse_args()
    
    print(f"🤖 Kimi K2.7 代碼生成器")
    print(f"📋 PR #{args.pr}")
    
    # 解析 features
    features = parse_planned_features(args.body)
    
    if not features:
        print("⚠️ 未能從 PR 描述中解析到 features")
        print("請確保 PR 描述包含 planned_features 區塊")
        sys.exit(1)
    
    print(f"📦 解析到 {len(features)} 個功能")
    
    created_prs = []
    
    for feature in features:
        print(f"\n{'='*60}")
        print(f"🔧 處理功能: {feature['name']}")
        
        # 生成代碼
        prompt = f"""你是一個專業的 Python/TypeScript 開發者。

請根據以下功能描述，生成完整的代碼：

## 功能名稱
{feature['name']}

## 功能描述
{feature.get('description', '無描述')}

## 代碼模板（可選）
{feature.get('code_template', '無模板，請根據描述自行設計')}

## 要求
1. 代碼必須完全可用，無佔位符
2. 遵循項目的代碼規範
3. 返回 JSON 格式：
{{
    "files": [
        {{
            "file_path": "路徑/文件名.擴展名",
            "content": "完整的文件內容"
        }}
    ],
    "summary": "變更摘要"
}}

請只返回 JSON，不要其他文字。
"""
        
        response = call_kimi(prompt)
        
        if not response:
            print(f"❌ Kimi API 調用失敗")
            continue
        
        # 解析響應
        try:
            # 嘗試提取 JSON
            json_match = re.search(r'```json\s*(.+?)\s*```', response, re.DOTALL)
            if json_match:
                code_data = json.loads(json_match.group(1))
            else:
                code_data = json.loads(response)
            
            files = code_data.get("files", [])
            summary = code_data.get("summary", "")
            
            if not files:
                print("⚠️ Kimi 未返回任何文件")
                continue
            
            # 創建 branch
            branch_name = create_branch(feature['name'])
            if not branch_name:
                print(f"❌ 創建 branch 失敗")
                continue
            
            print(f"🌿 Branch: {branch_name}")
            
            # 應用代碼變更
            if not apply_code_changes(files):
                print(f"❌ 應用代碼失敗")
                run_cmd(["git", "checkout", "main"])
                run_cmd(["git", "branch", "-D", branch_name])
                continue
            
            # 提交並推送
            if not commit_and_push(branch_name, feature['name']):
                print(f"❌ 提交失敗")
                run_cmd(["git", "checkout", "main"])
                run_cmd(["git", "branch", "-D", branch_name])
                continue
            
            # 創建 PR
            pr_number = create_pr(
                branch_name,
                feature['name'],
                feature.get('description', '') + f"\n\n{summary}"
            )
            
            if pr_number:
                print(f"✅ PR 已創建: #{pr_number}")
                created_prs.append(pr_number)
            else:
                print(f"⚠️ PR 創建失敗")
            
            # 切回 main
            run_cmd(["git", "checkout", "main"])
            
        except json.JSONDecodeError as e:
            print(f"❌ 解析 Kimi 響應失敗: {e}")
            print(f"原始響應:\n{response[:500]}...")
            continue
    
    # 總結
    print(f"\n{'='*60}")
    if created_prs:
        print(f"✅ 成功創建 {len(created_prs)} 個 PR:")
        for pr_num in created_prs:
            print(f"   #{pr_num}")
        
        # 在觸發的 PR 下留言
        comment_body = f"""## 🤖 AI DevOps 處理完成

成功生成 {len(created_prs)} 個功能 PR：

{chr(10).join([f'- #{pr}' for pr in created_prs])}

_由 Kimi K2.7 生成_"""
        
        run_cmd(["gh", "pr", "comment", str(args.pr), "--body", comment_body])
    else:
        print("❌ 沒有成功創建任何 PR")

if __name__ == "__main__":
    main()
