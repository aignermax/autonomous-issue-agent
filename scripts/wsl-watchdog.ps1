# WSL keep-alive watchdog.
#
# WSL terminates the distro (and every agent in it) as soon as the last
# wsl.exe client disconnects — systemd/linger inside the distro cannot
# prevent that. A single hidden keep-alive client works, but endpoint
# protection has been observed killing it (~30 min). This watchdog
# respawns the client within 60s, so the agents lose at most ~1 minute
# per kill and recover on their own (units are enabled + linger is on,
# so each distro boot restarts them automatically).
#
# Started at logon via the startup-folder VBS (wsl-agent-boot.vbs).

$ErrorActionPreference = 'SilentlyContinue'

while ($true) {
    $alive = Get-CimInstance Win32_Process -Filter "Name = 'wsl.exe'" |
        Where-Object { $_.CommandLine -match 'sleep infinity' }
    if (-not $alive) {
        Start-Process -WindowStyle Hidden -FilePath 'wsl.exe' -ArgumentList '--exec', 'sleep', 'infinity'
    }
    Start-Sleep -Seconds 60
}
