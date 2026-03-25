#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-10090}"
ACTION="${2:-register}"

case "$ACTION" in
  register)
    echo "Registering city to central registry..."
    curl -fsS -X POST "http://127.0.0.1:${PORT}/api/discovery/register-central"
    ;;
  pull-roles)
    echo "Pulling central roles policy..."
    curl -fsS -X POST "http://127.0.0.1:${PORT}/api/discovery/central/policy/roles/pull"
    ;;
  heartbeat)
    echo "Sending central heartbeat..."
    curl -fsS -X POST "http://127.0.0.1:${PORT}/api/discovery/central/heartbeat"
    ;;
  *)
    echo "Unknown action: $ACTION (use register|pull-roles|heartbeat)"
    exit 1
    ;;
esac

echo
echo "Done."
