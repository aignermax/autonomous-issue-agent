#!/bin/bash
# Control script for the autonomous issue agent
# Allows killing and restarting the agent and stuck Claude processes

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Find agent process
get_agent_pid() {
    pgrep -f "python.*main.py" | grep -v grep | head -1 || echo ""
}

# Find Claude processes that are children of the agent
get_claude_pids() {
    local agent_pid=$1
    if [ -z "$agent_pid" ]; then
        return
    fi

    # Find claude processes whose parent is the agent
    ps -eo pid,ppid,cmd | grep "claude" | grep -v grep | while read pid ppid cmd; do
        if [ "$ppid" = "$agent_pid" ]; then
            echo "$pid"
        fi
    done
}

# Check if agent is hung (low CPU + no activity)
is_agent_hung() {
    local agent_pid=$1
    if [ -z "$agent_pid" ]; then
        return 1
    fi

    # Check CPU usage
    local cpu=$(ps -p "$agent_pid" -o %cpu= | awk '{print $1}' | cut -d. -f1)

    # Check last log activity
    if [ -f "agent.log" ]; then
        local last_activity=$(stat -c %Y agent.log)
        local now=$(date +%s)
        local idle_time=$((now - last_activity))

        # Hung if: CPU < 1% AND no activity for > 20 minutes
        if [ "$cpu" -lt 1 ] && [ "$idle_time" -gt 1200 ]; then
            return 0
        fi
    fi

    return 1
}

# Commands
cmd_status() {
    echo -e "${BLUE}=== Agent Status ===${NC}"
    local agent_pid=$(get_agent_pid)

    if [ -z "$agent_pid" ]; then
        echo -e "${RED}❌ Agent NOT running${NC}"
        return
    fi

    echo -e "${GREEN}✓ Agent running${NC} (PID: $agent_pid)"

    # CPU usage
    local cpu=$(ps -p "$agent_pid" -o %cpu= | awk '{print $1}')
    echo "  CPU: ${cpu}%"

    # Last activity
    if [ -f "agent.log" ]; then
        local last_activity=$(stat -c %Y agent.log)
        local now=$(date +%s)
        local idle_mins=$(( (now - last_activity) / 60 ))
        echo "  Last activity: ${idle_mins}m ago"
    fi

    # Check for Claude children
    local claude_pids=$(get_claude_pids "$agent_pid")
    if [ -n "$claude_pids" ]; then
        echo -e "${BLUE}  Claude processes:${NC}"
        for cpid in $claude_pids; do
            local ccpu=$(ps -p "$cpid" -o %cpu= | awk '{print $1}')
            echo "    PID $cpid (CPU: ${ccpu}%)"
        done
    fi

    # Check if hung
    if is_agent_hung "$agent_pid"; then
        echo -e "${YELLOW}⚠️  WARNING: Agent appears to be HUNG${NC}"
        echo "    (Low CPU + no activity for >20min)"
    fi
}

cmd_kill() {
    echo -e "${YELLOW}Stopping agent...${NC}"
    local agent_pid=$(get_agent_pid)

    if [ -z "$agent_pid" ]; then
        echo -e "${RED}❌ Agent not running${NC}"
        return 1
    fi

    # Kill agent
    kill "$agent_pid" 2>/dev/null || true
    sleep 1

    # Check if still running
    if ps -p "$agent_pid" > /dev/null 2>&1; then
        echo -e "${YELLOW}Force killing agent...${NC}"
        kill -9 "$agent_pid" 2>/dev/null || true
    fi

    echo -e "${GREEN}✓ Agent stopped${NC}"
}

cmd_kill_claude() {
    echo -e "${YELLOW}Killing stuck Claude processes...${NC}"
    local agent_pid=$(get_agent_pid)

    if [ -z "$agent_pid" ]; then
        echo -e "${RED}❌ Agent not running${NC}"
        return 1
    fi

    local claude_pids=$(get_claude_pids "$agent_pid")
    if [ -z "$claude_pids" ]; then
        echo -e "${YELLOW}No Claude processes found${NC}"
        return
    fi

    for cpid in $claude_pids; do
        echo "  Killing Claude PID $cpid..."
        kill "$cpid" 2>/dev/null || true
    done

    sleep 1
    echo -e "${GREEN}✓ Claude processes killed${NC}"
    echo "  Agent should retry automatically"
}

cmd_restart() {
    echo -e "${BLUE}Restarting agent...${NC}"

    # Kill if running
    local agent_pid=$(get_agent_pid)
    if [ -n "$agent_pid" ]; then
        cmd_kill
    fi

    # Start agent
    echo -e "${GREEN}Starting agent...${NC}"
    ./run_agent.sh &
    sleep 2

    # Check if started
    agent_pid=$(get_agent_pid)
    if [ -n "$agent_pid" ]; then
        echo -e "${GREEN}✓ Agent restarted${NC} (PID: $agent_pid)"
    else
        echo -e "${RED}❌ Failed to start agent${NC}"
        return 1
    fi
}

cmd_logs() {
    if [ ! -f "agent.log" ]; then
        echo -e "${RED}❌ No agent.log found${NC}"
        return 1
    fi

    tail -f agent.log
}

cmd_help() {
    echo "Agent Control Script"
    echo ""
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  status        Show agent status (PID, CPU, hung detection)"
    echo "  kill          Stop the agent"
    echo "  kill-claude   Kill stuck Claude Code processes"
    echo "  restart       Restart the agent"
    echo "  logs          Tail agent.log (Ctrl+C to exit)"
    echo "  help          Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 status           # Check if agent is running"
    echo "  $0 kill-claude      # Kill hung Claude process"
    echo "  $0 restart          # Restart agent"
}

# Main
case "${1:-}" in
    status)
        cmd_status
        ;;
    kill)
        cmd_kill
        ;;
    kill-claude)
        cmd_kill_claude
        ;;
    restart)
        cmd_restart
        ;;
    logs)
        cmd_logs
        ;;
    help|--help|-h|"")
        cmd_help
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo ""
        cmd_help
        exit 1
        ;;
esac
