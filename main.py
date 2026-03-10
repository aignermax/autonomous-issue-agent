"""
Autonomous Issue Agent (AIA)

An autonomous agent that implements GitHub Issues using Claude Code.
Supports multi-session persistence for complex, long-running tasks.

Usage:
    python main.py          # Run continuously (polling mode)
    python main.py --once   # Run once and exit
"""

import sys
import logging
import os
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

    # Initialize agent
    agent = Agent(config)

    # Run mode
    if "--once" in sys.argv:
        log.info("Running in single-iteration mode")
        agent.run_once()
    else:
        log.info("Running in continuous polling mode")
        agent.run_forever()


if __name__ == "__main__":
    main()
