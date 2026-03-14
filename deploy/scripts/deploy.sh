#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "[deploy] Building and starting services..."
docker compose up -d postgres redis

echo "[deploy] Applying database migrations..."
docker compose run --rm city-api alembic upgrade head

echo "[deploy] Starting application services..."
docker compose up -d --build city-api city-worker

echo "[deploy] Done. Run deploy/scripts/verify.sh to validate service health."
