#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

TARGET_REVISION="${1:--1}"

echo "[rollback] Stopping application services."
docker compose stop city-api city-worker || true

echo "[rollback] Rolling back database migration to ${TARGET_REVISION}."
docker compose run --rm city-api alembic downgrade "${TARGET_REVISION}"

echo "[rollback] Restarting application services."
docker compose up -d city-api city-worker

echo "[rollback] Completed. Verify with deploy/scripts/verify.sh"
