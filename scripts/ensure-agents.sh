#!/bin/bash
# Idempotent agent starter — prevents duplicate agents by design.
#
# The three systemd user units (aia-coder / aia-qa / aia-prfeedback) are the
# single source of truth for running agents. This script:
#   1. kills stray agent processes NOT managed by systemd (old run.sh style)
#   2. leaves running units alone when their code is current
#   3. (re)starts units when they are inactive or the working-tree code is
#      newer than the running process (outdated agent)
#
# Called by run.sh (and thus start.bat / start-agent-autostart.bat). Safe to
# run any number of times.

set -u
cd "$(dirname "$0")/.." || exit 1

UNITS=(aia-coder aia-qa aia-prfeedback)

# --- 1. stray processes (not under systemd) --------------------------------
unit_pids=""
for u in "${UNITS[@]}"; do
    unit_pids="$unit_pids $(systemctl --user show "$u" -p MainPID --value 2>/dev/null)"
done
# Anchored match (^) — cmdline must BE the agent, not merely mention it
# (an unanchored pattern once matched the invoking shell and killed it).
# Any python path counts: dashboard-spawned strays run as
# "wsl-venv/bin/python3 main.py", units as "python3 main.py".
for pid in $(pgrep -f "^[^ ]*python[0-9.]* main\.py" 2>/dev/null); do
    [ "$pid" = "$$" ] && continue
    if ! grep -qw "$pid" <<<"$unit_pids"; then
        echo "[ensure-agents] stoppe verwaisten Agent-Prozess $pid (nicht systemd-verwaltet)"
        kill "$pid" 2>/dev/null
    fi
done

# --- 2./3. version-aware start/restart --------------------------------------
newest_code=$(find main.py src -name "*.py" -printf "%T@\n" 2>/dev/null \
    | sort -rn | head -1 | cut -d. -f1)

restart_needed=0
for u in "${UNITS[@]}"; do
    if [ "$(systemctl --user is-active "$u" 2>/dev/null)" = "active" ]; then
        started_ts=$(systemctl --user show "$u" -p ActiveEnterTimestamp --value 2>/dev/null)
        started=$(date -d "$started_ts" +%s 2>/dev/null || echo 0)
        if [ -n "$newest_code" ] && [ "$started" -lt "$newest_code" ]; then
            echo "[ensure-agents] $u läuft mit veraltetem Code (Start: $started_ts)"
            restart_needed=1
        fi
    else
        echo "[ensure-agents] $u ist nicht aktiv"
        restart_needed=1
    fi
done

if [ "$restart_needed" = "1" ]; then
    echo "[ensure-agents] starte/aktualisiere Units ..."
    systemctl --user restart "${UNITS[@]}"
    sleep 3
else
    echo "[ensure-agents] Agents laufen mit aktuellem Code — nichts zu tun"
fi

for u in "${UNITS[@]}"; do
    echo "  $u: $(systemctl --user is-active "$u")"
done
