#!/bin/bash
# AI DevOps Cron Job 設定腳本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# 設定 API Key
export KIMI_API_KEY="sk-kimi-8oT9paBmxuOegNMQq7G1oT8iGxz61V8P6NqJH9wQWfsbBdPk2HZFMJpoQbykbIcy"

# 執行 AI DevOps
cd "$REPO_ROOT"
python3 "$SCRIPT_DIR/ai_devops.py" >> "$SCRIPT_DIR/logs/ai_devops.log" 2>&1

# 清理舊日誌（保留 30 天）
find "$SCRIPT_DIR/logs" -name "*.log" -mtime +30 -delete
