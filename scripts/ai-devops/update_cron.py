import os
import subprocess

# Read current crontab
result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
current = result.stdout if result.returncode == 0 else ''

lines = []
for line in current.strip().split('\n'):
    if 'ai_devops.py' not in line:
        lines.append(line)

# Add new cronjob at 08:00 HKT
lines.append('0 8 * * * cd /Volumes/1.5T/develop/GitHub/ai-3kingdom && /usr/bin/python3 /Volumes/1.5T/develop/GitHub/ai-3kingdom/scripts/ai-devops/ai_devops.py >> /Volumes/1.5T/develop/GitHub/ai-3kingdom/scripts/ai-devops/logs/ai_devops.log 2>&1')

new_cron = '\n'.join(lines) + '\n'

# Install new crontab using EDITOR=true to avoid hanging
env = os.environ.copy()
env['EDITOR'] = 'true'
proc = subprocess.Popen(['crontab', '-'], stdin=subprocess.PIPE, env=env)
proc.communicate(input=new_cron.encode())

print("Done!")
print("\nNew crontab:")
result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
print(result.stdout)
