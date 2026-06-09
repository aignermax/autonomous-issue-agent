"""Tests for Agent._claim_won (atomic claim verification)."""

from unittest.mock import MagicMock


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
