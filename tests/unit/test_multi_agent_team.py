"""M6 multi-agent team tests."""

import json
from types import SimpleNamespace

from qdrant_client import QdrantClient

from capstone.agents.policy_agent import PolicyAgent
from capstone.llm.client import LLMClient
from capstone.memory.store import CustomerMemoryStore
from capstone.rag.hybrid import HybridPolicyRetriever
from capstone.rag.policy_index import PolicyIndex
from capstone.settings import Settings, get_settings
from capstone.team.multi_agent import MultiAgentTeam
from capstone.tools.repository import Repository


def _client(output: dict) -> LLMClient:
    def completion(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(output)))]
        )

    return LLMClient(Settings(llm_max_retries=0), completion=completion)


def _team(tmp_path, output: dict) -> MultiAgentTeam:
    policy_index = PolicyIndex(QdrantClient(":memory:"), get_settings().data_root / get_settings().domain)
    policy_index.build()
    return MultiAgentTeam(
        client=_client(output),
        repo=Repository(get_settings().seed_dir, tmp_path / "state"),
        memory_store=CustomerMemoryStore(tmp_path / "memory"),
        policy_index=policy_index,
        policy_agent=PolicyAgent(HybridPolicyRetriever(policy_index)),
    )


def test_m6_multi_agent_team_routes_legal_ticket_to_escalation_reviewer(tmp_path):
    output = {
        "issue_type": "refund_request",
        "order_ref": "KW-O-000950",
        "sentiment": "angry",
        "urgency": "critical",
        "claimed_amount_inr": 6499,
        "contact_number": 2,
        "escalation_signals": ["legal_or_regulatory"],
        "prompt_injection_suspected": False,
        "missing_fields": [],
        "summary": "Customer demands a refund and threatens legal action.",
    }

    result = _team(tmp_path, output).resolve(
        raw_text="Refund KW-O-000950 or I will file a legal complaint.",
        channel="email",
        customer_ref="KW-C-00285",
        today="2026-03-10",
    )

    assert [step.agent for step in result.steps] == [
        "Triage Agent",
        "Memory Agent",
        "Policy RAG Agent",
        "Order-Actions Agent",
        "Escalation Reviewer Agent",
    ]
    assert result.escalation_review["decision"] == "human_review"
    assert result.action_proposal["tool_name"] == "flag_for_human"
    assert result.policy_answer["grounded"]
    assert result.memory_context["ticket_count"] == 1


def test_m6_team_uses_same_tools_for_chat_and_email_channels(tmp_path):
    output = {
        "issue_type": "track_order",
        "order_ref": "KW-O-000950",
        "sentiment": "calm",
        "urgency": "normal",
        "claimed_amount_inr": None,
        "contact_number": 1,
        "escalation_signals": [],
        "prompt_injection_suspected": False,
        "missing_fields": [],
        "summary": "Customer asks where the order is.",
    }

    team = _team(tmp_path, output)
    email = team.resolve(
        raw_text="Where is order KW-O-000950?",
        channel="email",
        customer_ref="KW-C-00285",
        today="2026-03-10",
    )
    chat = team.resolve(
        raw_text="Track KW-O-000950",
        channel="chat",
        customer_ref="KW-C-00285",
        today="2026-03-10",
    )

    assert email.action_proposal["tool_name"] == "track_shipment"
    assert chat.action_proposal["tool_name"] == "track_shipment"
    assert email.action_proposal["tool_result"]["ok"]
    assert chat.action_proposal["tool_result"]["ok"]

