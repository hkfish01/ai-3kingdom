#!/usr/bin/env bash
set -euo pipefail

sshpass -p 'OneChain@1315' ssh -o StrictHostKeyChecking=no dell@100.64.0.5 'bash -s' <<'"'"'EOF'"'"'
set -euo pipefail
REPO=/home/dell/ai-3kingdom

cd "$REPO"
echo "[1] backup local modifications"
BACKUP=/home/dell/ai-3kingdom/.deploy-backup-$(date +%Y%m%d-%H%M%S)
mkdir -p "$BACKUP"
git diff --binary > "$BACKUP/local-changes.diff" || true
git ls-files --others --exclude-standard > "$BACKUP/untracked-files.txt" || true
tar -czf "$BACKUP/workspace.tar.gz" --exclude='.git' . || true

echo "[2] clean and hard reset to origin/main"
git reset --hard || true
git clean -fd || true
git fetch origin
git checkout -B master origin/main

echo "[3] fix compose paths"
sed -i 's#/home/rsadmin/develop/ai-3kingdom/deploy/prod/nginx.conf#/home/dell/ai-3kingdom/deploy/prod/nginx.conf#g' docker-compose.yml docker-compose.frontend-gateway.yml

echo "[4] stop old services"
docker compose down || true
docker compose -f docker-compose.frontend-gateway.yml down || true

echo "[5] rebuild images"
docker compose build --no-cache

echo "[6] start services"
docker compose up -d --build
docker compose -f docker-compose.frontend-gateway.yml up -d --build || true

echo "[7] wait and verify"
sleep 8
printf 'admin-dashboard status: '
curl -sS -o /tmp/admin.out -w "%{http_code}" http://127.0.0.1:10090/admin-dashboard || true
printf "\ncontainers:\n"
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
printf "\nfrontend logs:\n"
docker logs --tail 60 ai3k-frontend 2>&1 | tail -n 60 || true
printf "\ngateway logs:\n"
docker logs --tail 60 ai3k-gateway 2>&1 | tail -n 60 || true
EOF