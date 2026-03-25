#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "[verify] Checking container status..."
docker compose ps

echo "[verify] Checking API health..."
curl -fsS http://localhost:8000/health

echo "\n[verify] Recent city-api logs:"
docker compose logs --tail=100 city-api

echo "\n[verify] Recent city-worker logs:"
docker compose logs --tail=100 city-worker
