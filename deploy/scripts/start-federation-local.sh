#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="deploy/federation/docker-compose.federation.yml"

echo "[federation] Starting databases and redis..."
docker compose -f "$COMPOSE_FILE" up -d postgres-a postgres-b redis-a redis-b

echo "[federation] Applying migrations for city-a and city-b..."
docker compose -f "$COMPOSE_FILE" run --rm city-a alembic upgrade head
docker compose -f "$COMPOSE_FILE" run --rm city-b alembic upgrade head

echo "[federation] Starting city and worker services..."
docker compose -f "$COMPOSE_FILE" up -d city-a city-b worker-a worker-b

echo "[federation] Done. city-a=http://localhost:8100 city-b=http://localhost:8200"
