# Autostart Configuration for Autonomous Issue Agent

This guide helps you set up the agent to start automatically after Windows boots or updates.

## Why Autostart?

If your laptop automatically updates and reboots at night, the agent won't resume working unless you manually start it. Autostart ensures the agent restarts automatically after:
- Windows updates and reboots
- System crashes or power loss
- Manual reboots

## Option 1: Windows Task Scheduler (Recommended)

This is the most reliable method for Windows systems.

### Setup Steps:

1. **Open Task Scheduler**
   - Press `Win + R`
   - Type `taskschd.msc`
   - Press Enter

2. **Create Basic Task**
   - Click "Create Basic Task..." in the right panel
   - Name: `Autonomous Issue Agent Autostart`
   - Description: `Starts the autonomous issue agent in WSL after boot`
   - Click Next

3. **Trigger**
   - Select "When the computer starts"
   - Click Next

4. **Action**
   - Select "Start a program"
   - Click Next

5. **Program/Script**
   - Browse to: `C:\Users\MaxAigner\autonomous-issue-agent\start-agent-autostart.bat`
   - Or for PowerShell: `powershell.exe`
   - Add arguments (PowerShell): `-ExecutionPolicy Bypass -File "C:\Users\MaxAigner\autonomous-issue-agent\start-agent-autostart.ps1"`
   - Click Next

6. **Finish**
   - Check "Open the Properties dialog..."
   - Click Finish

7. **Properties Configuration (Important!)**
   - Go to "General" tab:
     - Select "Run whether user is logged on or not"
     - Check "Run with highest privileges"
   - Go to "Conditions" tab:
     - **UNCHECK** "Start the task only if the computer is on AC power" (important for laptops!)
     - Check "Wake the computer to run this task" (optional)
   - Go to "Settings" tab:
     - Check "Allow task to be run on demand"
     - Check "Run task as soon as possible after a scheduled start is missed"
     - Uncheck "Stop the task if it runs longer than" (agent should run indefinitely)
   - Click OK

### Test the Autostart

```powershell
# Test by running the task manually
schtasks /run /tn "Autonomous Issue Agent Autostart"

# Check if agent is running
wsl ps aux | grep python | grep agent
```

## Option 2: Windows Startup Folder (Simpler, but less reliable)

This method starts the agent when you log in (not at boot).

1. **Open Startup Folder**
   - Press `Win + R`
   - Type: `shell:startup`
   - Press Enter

2. **Create Shortcut**
   - Right-click in the folder
   - New → Shortcut
   - Location: `C:\Users\MaxAigner\autonomous-issue-agent\start-agent-autostart.bat`
   - Name: `Autonomous Issue Agent`

**Limitation:** Only starts when you log in, not after automatic reboots.

## Option 3: WSL Service (Advanced)

For a true service that starts with WSL:

```bash
# In WSL
sudo nano /etc/systemd/system/autonomous-agent.service
```

Add:
```ini
[Unit]
Description=Autonomous Issue Agent
After=network.target

[Service]
Type=simple
User=maxaigner
WorkingDirectory=/mnt/c/Users/MaxAigner/autonomous-issue-agent
ExecStart=/mnt/c/Users/MaxAigner/autonomous-issue-agent/run.sh
Restart=always
RestartSec=10
StandardOutput=append:/mnt/c/Users/MaxAigner/autonomous-issue-agent/agent.log
StandardError=append:/mnt/c/Users/MaxAigner/autonomous-issue-agent/agent.log

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable autonomous-agent.service
sudo systemctl start autonomous-agent.service
```

**Note:** This requires WSL2 with systemd enabled.

## Verify Autostart Works

After setting up autostart:

1. **Reboot your computer**
2. **Wait 1-2 minutes** for WSL to initialize
3. **Check if agent is running:**
   ```bash
   wsl ps aux | grep python | grep agent
   ```
4. **Check the dashboard:**
   ```bash
   wsl bash -c "cd /mnt/c/Users/MaxAigner/autonomous-issue-agent && python src/dashboard.py"
   ```

## Troubleshooting

### Agent doesn't start after reboot

**Check Task Scheduler History:**
- Open Task Scheduler
- Find your task
- Click "History" tab (bottom)
- Look for error messages

**Check error log:**
```powershell
# View autostart error log
Get-Content "$env:TEMP\agent-autostart-error.log"
```

**Common issues:**
- WSL not installed: Install with `wsl --install`
- Virtual environment not found: Check `run.sh` script
- Permissions: Run Task Scheduler as Administrator

### Agent starts but stops immediately

**Check agent logs:**
```bash
wsl tail -100 /mnt/c/Users/MaxAigner/autonomous-issue-agent/agent.log
```

**Common causes:**
- Missing `.env` file or invalid tokens
- Git repository access issues
- Network not ready (add delay in startup script)

### Add a startup delay (if network isn't ready)

Modify `start-agent-autostart.bat`:
```batch
@echo off
echo Waiting 30 seconds for network...
timeout /t 30 /nobreak
echo Starting Autonomous Issue Agent...
wsl bash -c "cd /mnt/c/Users/MaxAigner/autonomous-issue-agent && ./run.sh"
```

## Monitoring

To ensure the agent stays running, you can:

1. **Check status periodically:**
   ```bash
   wsl bash -c "cd /mnt/c/Users/MaxAigner/autonomous-issue-agent && python src/dashboard.py"
   ```

2. **Set up Windows notification** (optional):
   - Add to startup script to notify when agent starts
   - Use toast notifications: `msg * "Agent started successfully"`

3. **Remote monitoring:**
   - Check GitHub for recent PR activity
   - Monitor agent logs remotely if you have SSH access

## Updating After Autostart is Configured

When you `git pull` updates from home, the agent will:
- Continue running with old code until next restart
- Automatically use new code after next Windows reboot

To apply updates immediately without reboot:
```bash
# Stop current agent
wsl pkill -f "python.*main.py"

# Start with new code
wsl bash -c "cd /mnt/c/Users/MaxAigner/autonomous-issue-agent && ./run.sh"
```

## Security Considerations

- The startup script runs with your user permissions
- GitHub tokens and API keys are stored in `.env` (not in startup script)
- Agent has access to repositories configured in `.env`
- Consider encrypting `.env` file if laptop is shared

## Disabling Autostart

**Task Scheduler method:**
- Open Task Scheduler
- Find "Autonomous Issue Agent Autostart"
- Right-click → Disable

**Startup Folder method:**
- Press `Win + R` → `shell:startup`
- Delete the shortcut

## Summary

✅ **Recommended setup:** Task Scheduler with `start-agent-autostart.bat`
✅ **Starts after:** Windows updates, reboots, power loss
✅ **No manual intervention:** Agent resumes automatically
✅ **Easy to disable:** Via Task Scheduler

After setup, your agent will work 24/7, even after automatic updates! 🎉
