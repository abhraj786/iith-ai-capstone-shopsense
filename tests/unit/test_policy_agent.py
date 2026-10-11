"""M4 policy agent tests."""

from qdrant_client import QdrantClient

from capstone.agents.policy_agent import PolicyAgent
from capstone.rag.hybrid import HybridPolicyRetriever
from capstone.rag.policy_index import PolicyIndex
from capstone.settings import PROJECT_ROOT


def _agent():
    index = PolicyIndex(QdrantClient(":memory:"), PROJECT_ROOT / "data" / "shopsense")
    index.build()
    return PolicyAgent(HybridPolicyRetriever(index))


def test_policy_agent_answers_beauty_window_without_inventing_30_days():
    answer = _agent().answer("Can a customer return an opened Beauty item after 11 days?")
    text = " ".join([answer.answer, *answer.evidence])
    assert answer.grounded
    assert "Beauty" in text and "10" in text and "opened" in text.lower()
    assert "30 days" not in answer.answer
    assert answer.citations


def test_policy_agent_answers_auto_refund_cap_with_citation():
    answer = _agent().answer("What is the automated assistant refund approval cap?")
    text = " ".join([answer.answer, *answer.evidence])
    assert answer.grounded
    assert "2,000" in text
    assert any(c.document_slug == "refund-authority" for c in answer.citations)
