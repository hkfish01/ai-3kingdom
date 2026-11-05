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
| `KIMI_API_KEY` | Optional, currently **not configured**. If you enable AI DevOps, create your own key and keep it out of the repo: launchd reads it from macOS Keychain, CI from a GitHub Actions secret |
| `OBSIDIAN_VAULT` | Path to Obsidian vault |
| `PATH` | Must include `/opt/homebrew/bin` for `gh` CLI |

## CI status (verified 2026-11-05)

AI DevOps is **disabled by default**. The repository has only three Actions
secrets (`ADMIN_REFRESH_TOKEN`, `JUMP_HOST_PASSWORD`, `PROD_HOST_PASSWORD`) —
there is **no `KIMI_API_KEY` and no `AI_DEVOPS_REDIS_URL`**. The old daily
schedule therefore never performed any real review, and its `deploy` job could
never legitimately auto-merge a PR.

`.github/workflows/ai-devops.yml` now runs only via manual `workflow_dispatch`
and exits cleanly with a notice when the secrets are missing. To enable it:

1. Add both secrets in **Settings → Secrets and variables → Actions**.
2. Optionally set repository variable `AI_DEVOPS_AUTO_MERGE=true` — without it,
   the `deploy` job will never merge a PR or trigger a production deploy.
3. Re-run the workflow manually. Only add `schedule` / `repository_dispatch`
   back to `on:` after a successful run.

For local launchd runs, store the key in the macOS Keychain instead:

```sh
security add-generic-password -U -a "$USER" -s ai-3kingdom-kimi -w 'YOUR_KEY'
```

> **Credentials:** this project has never had a Kimi credential configured, so
> there is nothing to revoke or rotate. If you decide to enable AI DevOps, create
> your own key and store it in macOS Keychain / GitHub Actions secrets. Never put
> keys in `.env.example`, plists, workflow files, or git history.
