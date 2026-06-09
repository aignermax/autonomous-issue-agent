"""Tests for Agent._claim_won (atomic claim verification)."""

from unittest.mock import MagicMock, patch


def _make_agent(agent_id="host:me123456"):
    from src.agent import Agent
    agent = Agent.__new__(Agent)
    agent.agent_id = agent_id
    agent.github = MagicMock()
    return agent


class TestClaimWon:
    def test_won_when_winner_is_self(self):
        agent = _make_agent("host:me123456")
        agent.github.claim_winner.return_value = "host:me123456"
        issue = MagicMock(number=1)
        assert agent._claim_won(issue) is True

    def test_won_when_winner_is_none_failsafe(self):
        agent = _make_agent()
        agent.github.claim_winner.return_value = None
        issue = MagicMock(number=1)
        assert agent._claim_won(issue) is True

    def test_lost_when_winner_is_other(self):
        agent = _make_agent("host:me123456")
        agent.github.claim_winner.return_value = "other:zzzz9999"
        issue = MagicMock(number=1)
        assert agent._claim_won(issue) is False

    def test_lost_when_post_claim_fails(self):
        agent = _make_agent("host:me123456")
        agent.github.post_claim.side_effect = Exception("comment API down")
        issue = MagicMock(number=1)
        assert agent._claim_won(issue) is False


class TestProcessIssueClaimLoss:
    def test_loser_returns_early_without_worktree(self):
        from src.agent import Agent, IssueResult
        agent = Agent.__new__(Agent)
        agent.agent_id = "host:me123456"
        agent.session_manager = MagicMock()
        agent.session_manager.load_state.return_value = None  # new issue
        agent.worktrees = MagicMock()
        agent._claim_issue_and_create_branch = MagicMock(return_value="agent/issue-99-1")
        agent._claim_won = MagicMock(return_value=False)

        issue = MagicMock(number=99)
        result = agent.process_issue(issue)

        assert result.success is False
        assert result.lost_claim_race is True
        agent.worktrees.create.assert_not_called()
