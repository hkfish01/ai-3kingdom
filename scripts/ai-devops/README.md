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
| `KIMI_API_KEY` | Moonshot Kimi API key — **請勿寫進版本庫或 plist**。launchd 設定會從 macOS Keychain 讀取；CI 用 GitHub Actions secret |
| `OBSIDIAN_VAULT` | Path to Obsidian vault |
| `PATH` | Must include `/opt/homebrew/bin` for `gh` CLI |

> **Security notice:** a KIMI key was once committed in plaintext (both
> `deploy/prod/.env.example` and this plist). Treat it as compromised: revoke and
> rotate it in the Moonshot console, then update **GitHub Actions secret
> `KIMI_API_KEY`**, the production `deploy/prod/.env`, and the local Keychain:
>
> ```sh
> security add-generic-password -U -a "$USER" -s ai-3kingdom-kimi -w 'YOUR_NEW_KEY'
> ```
>
> Removing the value from the working tree does **not** remove it from git history.
