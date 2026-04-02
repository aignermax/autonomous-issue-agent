# Autonomous Issue Agent - Autostart Script (PowerShell)
# This script starts the agent in WSL after Windows boots

Write-Host "Starting Autonomous Issue Agent in WSL..." -ForegroundColor Green
Write-Host "Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

# Change to agent directory in WSL and start
$wslCommand = "cd /mnt/c/Users/MaxAigner/autonomous-issue-agent && ./run.sh"

try {
    # Start WSL with the agent
    wsl bash -c $wslCommand

    Write-Host "Agent started successfully" -ForegroundColor Green
}
catch {
    $errorMsg = "ERROR: Failed to start agent at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`n$($_.Exception.Message)"
    Write-Host $errorMsg -ForegroundColor Red

    # Log error to file
    $errorMsg | Out-File -Append "$env:TEMP\agent-autostart-error.log"
}
