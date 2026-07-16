"""
One-shot demo runner: process a single Lunima issue from start to finish.

Bypasses the round-robin scheduler so we can target a specific issue on
a specific repo without rewriting `Agent.run_single_issue` (which always
picks `repo_names[0]`). Reads .env, then forces `AGENT_REPOS` to Lunima
so the first (and only) repo IS Lunima.

Usage:
    python demo_run.py <issue_number>
"""

import logging
import os
import sys

from dotenv import load_dotenv

# load .env first, then override the repo list — load_dotenv(override=True)
# would otherwise stomp on whatever we set above it.
load_dotenv(override=True)
os.environ["AGENT_REPOS"] = "aignermax/Lunima"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("agent_demo.log")],
)
log = logging.getLogger("agent")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: demo_run.py <issue_number>", file=sys.stderr)
        return 2

    try:
        issue_number = int(sys.argv[1])
    except ValueError:
        print(f"not a valid issue number: {sys.argv[1]}", file=sys.stderr)
        return 2

    from src.agent import Agent
    from src.config import Config

    config = Config()
    missing = config.validate()
    if missing:
        log.error(f"Missing env vars: {missing}")
        return 1

    log.info(f"Demo run: aignermax/Lunima issue #{issue_number}")
    agent = Agent(config)
    agent.run_single_issue(issue_number)
    log.info("Demo run finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
