# AI DevOps Local Setup

## macOS Launchd Notes

**SIP Restriction:** macOS System Integrity Protection (SIP) blocks launchd processes from
executing Python scripts on external volumes (`/Volumes/...`). The script must run from
a local path (`/Users/terry/scripts/`).

## Setup Steps

1. **Copy script to local path:**
   ```bash
   ./scripts/ai-devops/sync_to_local.sh
   ```
   Run this after every `git pull` to sync the latest script.

2. **Install the launchd agent:**
   ```bash
   cp deploy/macos/ai-3kingdom.ai-devops.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/ai-3kingdom.ai-devops.plist
   ```

3. **Trigger manually for testing:**
   ```bash
   launchctl kickstart -p gui/$(id -u)/ai-3kingdom.ai-devops
   ```

4. **View logs:**
   ```bash
   cat ~/scripts/logs/ai_devops.log
   ```

## Environment Variables (set in plist)

| Variable | Description |
|---|---|
| `KIMI_API_KEY` | Moonshot Kimi API key |
| `OBSIDIAN_VAULT` | Path to Obsidian vault |
| `PATH` | Must include `/opt/homebrew/bin` for `gh` CLI |
