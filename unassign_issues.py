#!/usr/bin/env python3
"""Un-assign all agent-task issues so the agent can pick them up."""

from dotenv import load_dotenv
load_dotenv(override=True)
from src.github_client import GitHubClient

gh = GitHubClient('Akhetonics/akhetonics-desktop')

print('Removing assignees from agent-task issues...')
count = 0
for issue in gh.repo.get_issues(state='open', labels=['agent-task']):
    if not issue.pull_request and issue.assignees:
        print(f'  Issue #{issue.number}: {issue.title}')
        print(f'    Current assignees: {[a.login for a in issue.assignees]}')
        issue.remove_from_assignees(*issue.assignees)
        print(f'    ✅ Removed all assignees')
        count += 1

print(f'\nDone! Un-assigned {count} issues. Agent can now pick them up.')
