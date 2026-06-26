#!/bin/bash
set -euo pipefail

PLIST_SRC="/Volumes/1.5T/develop/GitHub/ai-3kingdom/deploy/macos/ai-3kingdom.ai-devops.plist"
PLIST_DST="$HOME/Library/LaunchAgents/ai-3kingdom.ai-devops.plist"
LOG_DIR="/Volumes/1.5T/develop/GitHub/ai-3kingdom/scripts/ai-devops/logs"

mkdir -p "$LOG_DIR"
mkdir -p "$HOME/Library/LaunchAgents"

cp -f "$PLIST_SRC" "$PLIST_DST"
chmod 644 "$PLIST_DST"

if launchctl list | grep -q "ai-3kingdom.ai-devops"; then
  launchctl unload "$PLIST_DST" || true
fi

launchctl load "$PLIST_DST"
echo "Installed launchd job: ai-3kingdom.ai-devops"
