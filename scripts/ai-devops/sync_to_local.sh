#!/bin/bash
# Sync script: copy ai_devops.py from repo to ~/scripts for launchd
# Run this after every `git pull` in the ai-3kingdom repo
cp /Volumes/1.5T/develop/GitHub/ai-3kingdom/scripts/ai-devops/ai_devops.py ~/scripts/ai_devops.py
echo "✅ Synced ai_devops.py to ~/scripts"
