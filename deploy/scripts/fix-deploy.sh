#!/usr/bin/env bash
set -euo pipefail

cd ~/ai-3kingdom || exit 1

echo "=== current branch and remotes ==="
git branch --show-current || true
git branch -a | sed -n '1,40p'
git remote -v | sed -n '1,20p'

echo "=== determine upstream branch ==="
up=""
if git show-ref --verify --quiet refs/remotes/origin/main; then
  up=origin/main
elif git show-ref --verify --quiet refs/remotes/origin/master; then
  up=origin/master
else
  up=""
fi
echo "upstream=$up"

echo "=== checkout upstream branch if missing ==="
if [ -n "$up" ]; then
  branch="${up#origin/}"
  if [ "$(git branch --show-current)" != "$branch" ]; then
    git checkout -f "$branch" || git checkout -B "$branch" "$up"
  fi
  git reset --hard "$up"
else
  echo "no upstream branch found"
  exit 1
fi

echo "=== reset compose paths ==="
sed -i 's#/home/rsadmin/develop/ai-3kingdom/deploy/prod/nginx.conf#/home/dell/ai-3kingdom/deploy/prod/nginx.conf#g' docker-compose.yml docker-compose.frontend-gateway.yml

echo "=== docker compose down ==="
docker compose down || true
docker compose -f docker-compose.frontend-gateway.yml down || true

echo "=== build and start ==="
docker compose build --no-cache
docker compose up -d --build

echo "=== start gateway if exists ==="
docker compose -f docker-compose.frontend-gateway.yml build --no-cache || true
docker compose -f docker-compose.frontend-gateway.yml up -d --build || true

echo "=== verify routes ==="
sleep 5
curl -sS http://127.0.0.1:10090/admin-dashboard | head -c 200 || true
printf '\n'
curl -sS -o /tmp/admin-dashboard.out -w "%{http_code}" http://127.0.0.1:10090/admin-dashboard || true
printf '\n'
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
docker logs --tail 60 ai3k-frontend 2>&1 | tail -n 60 || true
