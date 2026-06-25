#!/usr/bin/env bash
set -euo pipefail

# =============================================
# AI Three Kingdoms - AI DevOps Dashboard 部署腳本
# =============================================

echo "=========================================="
echo "AI Three Kingdoms - 部署 AI DevOps Dashboard"
echo "=========================================="

# 1. 停止現有服務
echo "[1/5] 停止現有服務..."
docker compose down

# 2. 構建後端（含 AI DevOps）
echo "[2/5] 構建後端服務..."
docker compose build city-api city-worker

# 3. 啟動資料庫
echo "[3/5] 啟動資料庫..."
docker compose up -d postgres redis

# 4. 等待資料庫就緒
echo "[4/5] 等待資料庫就緒..."
sleep 5

# 5. 執行資料庫遷移
echo "[5/5] 執行資料庫遷移..."
docker compose run --rm city-api alembic upgrade head

# 6. 啟動所有服務
echo "[6/6] 啟動所有服務..."
docker compose up -d

echo ""
echo "=========================================="
echo "部署完成！"
echo "=========================================="
echo ""
echo "服務地址："
echo "  - API: http://100.64.0.5:10090"
echo "  - 前端: http://100.64.0.5:10090"
echo "  - Admin Dashboard: http://100.64.0.5:10090/admin-dashboard"
echo "  - Admin 登入: http://100.64.0.5:10090/admin/login"
echo ""
echo "管理員登入："
echo "  - 帳號: terry"
echo "  - 密碼: 12341234"
echo ""
echo "AI DevOps 功能："
echo "  - 每天 UTC 02:00 自動執行健康檢查"
echo "  - 手動觸發: POST /api/admin/devops/trigger"
echo "  - 查看報告: GET /api/admin/devops/report"
echo "=========================================="
