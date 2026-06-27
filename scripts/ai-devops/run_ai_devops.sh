#!/bin/bash
# Wrapper for ai_devops.py to work around launchd python3 execution issues
exec /usr/bin/python3 /Volumes/1.5T/develop/GitHub/ai-3kingdom/scripts/ai-devops/ai_devops.py \
    >> /Volumes/1.5T/develop/GitHub/ai-3kingdom/scripts/ai-devops/logs/ai_devops.log 2>&1
