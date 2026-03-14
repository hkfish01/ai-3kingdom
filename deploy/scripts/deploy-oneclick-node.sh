#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/deploy/prod/.env}"
COMPOSE_FILE="$ROOT_DIR/deploy/prod/docker-compose.server.yml"

CITY_NAME="${CITY_NAME:-Luoyang}"
CITY_BASE_URL="${CITY_BASE_URL:-http://localhost:10090}"
CITY_LOCATION="${CITY_LOCATION:-Unknown}"
WORLD_NAME="${WORLD_NAME:-Three Kingdoms Autonomous World}"
CITY_WALL="${CITY_WALL:-300}"
CITY_TAX_RATE="${CITY_TAX_RATE:-0.05}"
OPEN_FOR_MIGRATION="${OPEN_FOR_MIGRATION:-true}"
PROTOCOL_VERSION="${PROTOCOL_VERSION:-1.0}"
RULE_VERSION="${RULE_VERSION:-1.0}"
GATEWAY_PORT="${GATEWAY_PORT:-10090}"
CENTRAL_REGISTRY_URL="${CENTRAL_REGISTRY_URL:-}"
CENTRAL_REGISTRY_TOKEN="${CENTRAL_REGISTRY_TOKEN:-}"
CENTRAL_ROLES_POLICY_URL="${CENTRAL_ROLES_POLICY_URL:-}"
CENTRAL_HEARTBEAT_URL="${CENTRAL_HEARTBEAT_URL:-}"
CENTRAL_NODE_ID="${CENTRAL_NODE_ID:-}"
CENTRAL_ROLES_POLICY_REQUIRED="${CENTRAL_ROLES_POLICY_REQUIRED:-false}"
ADMIN_USERNAMES="${ADMIN_USERNAMES:-}"
PASSWORD_RESET_CODE_TTL_MINUTES="${PASSWORD_RESET_CODE_TTL_MINUTES:-15}"
SMTP_HOST="${SMTP_HOST:-}"
SMTP_PORT="${SMTP_PORT:-587}"
SMTP_USER="${SMTP_USER:-}"
SMTP_PASSWORD="${SMTP_PASSWORD:-}"
SMTP_FROM="${SMTP_FROM:-}"
SMTP_USE_TLS="${SMTP_USE_TLS:-true}"

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required."
  exit 1
fi

JWT_SECRET="${JWT_SECRET:-$(openssl rand -hex 48)}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$(openssl rand -base64 36 | tr -d '\n' | tr '/+' 'AB' | cut -c1-40)}"
FEDERATION_SHARED_SECRET="${FEDERATION_SHARED_SECRET:-$(openssl rand -hex 48)}"

mkdir -p "$(dirname "$ENV_FILE")"
cat >"$ENV_FILE" <<EOF
JWT_SECRET=${JWT_SECRET}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
FEDERATION_SHARED_SECRET=${FEDERATION_SHARED_SECRET}
CITY_NAME=${CITY_NAME}
CITY_BASE_URL=${CITY_BASE_URL}
CITY_LOCATION=${CITY_LOCATION}
WORLD_NAME=${WORLD_NAME}
CITY_WALL=${CITY_WALL}
CITY_TAX_RATE=${CITY_TAX_RATE}
OPEN_FOR_MIGRATION=${OPEN_FOR_MIGRATION}
PROTOCOL_VERSION=${PROTOCOL_VERSION}
RULE_VERSION=${RULE_VERSION}
GATEWAY_PORT=${GATEWAY_PORT}
CENTRAL_REGISTRY_URL=${CENTRAL_REGISTRY_URL}
CENTRAL_REGISTRY_TOKEN=${CENTRAL_REGISTRY_TOKEN}
CENTRAL_ROLES_POLICY_URL=${CENTRAL_ROLES_POLICY_URL}
CENTRAL_HEARTBEAT_URL=${CENTRAL_HEARTBEAT_URL}
CENTRAL_NODE_ID=${CENTRAL_NODE_ID}
CENTRAL_ROLES_POLICY_REQUIRED=${CENTRAL_ROLES_POLICY_REQUIRED}
ADMIN_USERNAMES=${ADMIN_USERNAMES}
PASSWORD_RESET_CODE_TTL_MINUTES=${PASSWORD_RESET_CODE_TTL_MINUTES}
SMTP_HOST=${SMTP_HOST}
SMTP_PORT=${SMTP_PORT}
SMTP_USER=${SMTP_USER}
SMTP_PASSWORD=${SMTP_PASSWORD}
SMTP_FROM=${SMTP_FROM}
SMTP_USE_TLS=${SMTP_USE_TLS}
AUTO_CREATE_SCHEMA=false
EOF

chmod 600 "$ENV_FILE"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d postgres redis
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" run --rm city-api alembic upgrade head
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build city-api city-worker frontend gateway
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" restart gateway

sleep 2
echo "Health:"
curl -fsS "http://127.0.0.1:${GATEWAY_PORT}/health" || true
echo

if [[ -n "$CENTRAL_REGISTRY_URL" ]]; then
  echo "Registering this city to central registry..."
  curl -fsS -X POST "http://127.0.0.1:${GATEWAY_PORT}/api/discovery/register-central" || true
  echo
fi

if [[ -n "$CENTRAL_ROLES_POLICY_URL" ]]; then
  echo "Pulling central roles policy..."
  curl -fsS -X POST "http://127.0.0.1:${GATEWAY_PORT}/api/discovery/central/policy/roles/pull" || true
  echo
fi

if [[ -n "$CENTRAL_HEARTBEAT_URL" ]]; then
  echo "Sending initial central heartbeat..."
  curl -fsS -X POST "http://127.0.0.1:${GATEWAY_PORT}/api/discovery/central/heartbeat" || true
  echo
fi

echo "Done. Node is running on port ${GATEWAY_PORT}."
