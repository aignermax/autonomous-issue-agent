# WSL keep-alive watchdog.
#
# WSL terminates the distro (and every agent in it) as soon as the last
# wsl.exe client disconnects — systemd/linger inside the distro cannot
# prevent that. This watchdog keeps one hidden client alive and respawns
# it within 60s if it disappears (e.g. window closed by accident), so
# the agents lose at most ~1 minute and recover on their own (units are
# enabled + linger is on, so each distro boot restarts them).
#
# Started at logon via the startup-folder VBS (wsl-agent-boot.vbs),
# which launches it fully hidden. The title/output below exist so that
# if the window ever becomes visible, it explains itself instead of
# being a scary empty box.

$ErrorActionPreference = 'SilentlyContinue'

$Host.UI.RawUI.WindowTitle = 'WSL Agent Watchdog - BITTE NICHT SCHLIESSEN (haelt die autonomen Agents am Leben)'
Write-Output '=================================================================='
Write-Output ' WSL Agent Watchdog'
Write-Output ' Haelt die WSL-Distro (und damit coder/qa/pr-feedback) am Leben.'
Write-Output ' Dieses Fenster ist normalerweise unsichtbar. BITTE NICHT SCHLIESSEN.'
Write-Output ' Agents stoppen: Desktop -> stop-agents.cmd'
Write-Output '=================================================================='

while ($true) {
    $alive = Get-CimInstance Win32_Process -Filter "Name = 'wsl.exe'" |
        Where-Object { $_.CommandLine -match 'sleep infinity' }
    if (-not $alive) {
        Start-Process -WindowStyle Hidden -FilePath 'wsl.exe' -ArgumentList '--exec', 'sleep', 'infinity'
        Write-Output "$(Get-Date -Format 'HH:mm:ss') keep-alive client neu gestartet"
    }
    Start-Sleep -Seconds 60
}
