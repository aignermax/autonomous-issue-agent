"""
Agent role implementations.

Each agent is a polling worker with a specific role:
- coder: implements GitHub Issues into PRs (existing src/agent.py)
- qa:    verifies PRs created by the coder (build + test gate)

Future roles (not implemented yet): pm, architect.
"""
