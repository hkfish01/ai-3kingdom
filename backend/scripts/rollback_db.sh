#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TARGET_REVISION="${1:--1}"

echo "[db-rollback] downgrading to ${TARGET_REVISION}"
alembic downgrade "$TARGET_REVISION"
