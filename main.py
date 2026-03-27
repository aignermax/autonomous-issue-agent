"""
Autonomous Issue Agent (AIA)

An autonomous agent that implements GitHub Issues using Claude Code.
Supports multi-session persistence for complex, long-running tasks.

Usage:
    python main.py                  # Run continuously (polling mode)
    python main.py --once           # Run once and exit
    python main.py --once 242       # Process specific issue and exit
"""

import sys
import logging
import os
import argparse
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from src.config import Config
from src.agent import Agent


# ==============================
# LOGGING
# ==============================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("agent.log"),
    ],
)
log = logging.getLogger("agent")


# ==============================
# ENTRY POINT
# ==============================

def main():
    """Main entry point."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Autonomous Issue Agent")
    parser.add_argument("--once", nargs='?', const=True, type=int,
                        help="Run once and exit (optionally specify issue number)")
    args = parser.parse_args()

    # Warn if running inside Claude Code session
    if os.environ.get("CLAUDECODE"):
        log.warning("=" * 60)
        log.warning("WARNING: Running inside a Claude Code session!")
        log.warning("This may cause nested session conflicts.")
        log.warning("Recommended: Run in a separate terminal window.")
        log.warning("=" * 60)
        # Don't exit - user might have unset it intentionally via .bat file

    # Load configuration
    config = Config()

    # Validate required environment variables
    missing = config.validate()
    if missing:
        log.error(f"Missing environment variables: {', '.join(missing)}")
        log.error("Please create a .env file with your credentials:")
        log.error("  cp .env.example .env")
        log.error("Then add your tokens to .env and run ./run_agent.sh")
        sys.exit(1)

    # Check development environment (warn about missing tools)
    import shutil
    import platform

    is_wsl = "microsoft" in platform.uname().release.lower()

    if is_wsl:
        log.info("🐧 Running in WSL (Windows Subsystem for Linux)")

        # Check for dotnet
        if not shutil.which("dotnet"):
            log.warning("⚠️  dotnet not found in WSL!")
            log.warning("    If your repository uses .NET, the agent may struggle with:")
            log.warning("    - Building projects")
            log.warning("    - Running tests")
            log.warning("    - Understanding project structure")
            log.warning("")
            log.warning("    To install dotnet in WSL:")
            log.warning("    wget https://dot.net/v1/dotnet-install.sh")
            log.warning("    chmod +x dotnet-install.sh")
            log.warning("    ./dotnet-install.sh --channel 8.0")
            log.warning("")

    # Check for common dev tools
    if not shutil.which("git"):
        log.error("❌ git not found - required for agent operation!")
        sys.exit(1)

    # Initialize agent
    agent = Agent(config)

    # Run mode
    if args.once is not None:
        if isinstance(args.once, int):
            log.info(f"Running in single-issue mode for issue #{args.once}")
            agent.run_single_issue(args.once)
        else:
            log.info("Running in single-iteration mode")
            agent.run_once()
    else:
        log.info("Running in continuous polling mode")
        agent.run_forever()


if __name__ == "__main__":
    main()
