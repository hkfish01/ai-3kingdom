#!/bin/bash
# AI DevOps Cron Job 設定腳本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# 每日凌晨 2 點執行（可調整）
CRON_EXPRESSION="0 2 * * *"

# Cron job 命令
CRON_CMD="cd $REPO_ROOT && /usr/bin/python3 $SCRIPT_DIR/ai_devops.py >> $SCRIPT_DIR/logs/ai_devops.log 2>&1"

echo "🤖 AI DevOps Cron Job 設定"
echo "=========================================="
echo "📁 Repo: $REPO_ROOT"
echo "⏰ Cron: $CRON_EXPRESSION"
echo ""

# 創建 logs 目錄
mkdir -p "$SCRIPT_DIR/logs"

# 檢查是否已有相同的 cron job
EXISTING=$(crontab -l 2>/dev/null | grep -F "$SCRIPT_DIR/ai_devops.py" | head -1)

if [ -n "$EXISTING" ]; then
    echo "⚠️  已有 AI DevOps cron job:"
    echo "   $EXISTING"
    echo ""
    echo "要移除嗎？ (y/N)"
    read -r confirm
    if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
        crontab -l 2>/dev/null | grep -Fv "$SCRIPT_DIR/ai_devops.py" | crontab -
        echo "✅ 已移除"
    fi
else
    # 添加新的 cron job
    echo "📝 添加 cron job..."
    
    # 保留現有 crontab，添加新的 job
    (crontab -l 2>/dev/null; echo "$CRON_EXPRESSION $CRON_CMD") | crontab -
    
    echo "✅ Cron job 已添加"
fi

echo ""
echo "=========================================="
echo "📋 當前 Crontab:"
echo "-------------------------------------------"
crontab -l 2>/dev/null || echo "(空)"
echo "=========================================="
echo ""
echo "💡 手動測試:"
echo "   cd $REPO_ROOT && python3 $SCRIPT_DIR/ai_devops.py"
echo ""
echo "📜 查看日誌:"
echo "   tail -f $SCRIPT_DIR/logs/ai_devops.log"
