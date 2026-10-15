"""M6 multi-agent team tests."""

import json
from types import SimpleNamespace

from qdrant_client import QdrantClient

from capstone.agents.policy_agent import PolicyAgent
from capstone.llm.client import LLMClient
from capstone.mcp.client import MCPShopSenseToolGateway, ShopSenseMCPClient
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


def test_m6_team_can_call_order_tool_through_mcp_protocol(tmp_path):
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
    team.tool_gateway = MCPShopSenseToolGateway(
        ShopSenseMCPClient(env={"CAPSTONE_RUNTIME_ROOT": str(tmp_path / "mcp-runtime")})
    )

    result = team.resolve(
        raw_text="Track KW-O-000950",
        channel="chat",
        customer_ref="KW-C-00285",
        today="2026-03-10",
    )

    assert result.action_proposal["tool_name"] == "track_shipment"
    assert result.action_proposal["tool_result"]["transport"] == "mcp"
    assert result.steps[3].summary.endswith("via mcp.")



_CALM_REFUND = {
    "issue_type": "refund_request", "order_ref": "KW-O-000950", "sentiment": "calm",
    "urgency": "normal", "claimed_amount_inr": None, "contact_number": 1,
    "escalation_signals": [], "prompt_injection_suspected": False,
    "missing_fields": [], "summary": "Customer asks for a refund.",
}


def test_m6_write_scopes_are_enforced():
    import pytest
    from capstone.team.multi_agent import AGENT_SCOPES, commit

    board: dict = {}
    commit(board, "Policy RAG Agent", policy_answer="ok")
    with pytest.raises(PermissionError, match="outside its scope"):
        commit(board, "Escalation Reviewer Agent", review={}, proposal="rewritten")
    assert "proposal" not in board
    assert len(AGENT_SCOPES) == 5


def test_m6_reviewer_catches_risk_the_planner_missed():
    from capstone.schemas.actions import ActionProposal, RecommendedAction
    from capstone.schemas.intake import SupportTicket

    ticket = SupportTicket.model_validate({**_CALM_REFUND, "sentiment": "angry"})
    auto = ActionProposal(recommended_action=RecommendedAction.refund, explanation="x",
                          tool_name="issue_refund", tool_args={})
    review = MultiAgentTeam.review_case(ticket, auto)
    assert review["decision"] == "human_review"
    assert review["overrode_order_actions"] is True

    calm = SupportTicket.model_validate(_CALM_REFUND)
    assert MultiAgentTeam.review_case(calm, auto)["decision"] == "auto_resolve"


def test_m6_reviewer_runs_before_any_write(tmp_path):
    output = {**_CALM_REFUND, "sentiment": "angry", "claimed_amount_inr": 500}
    team = _team(tmp_path, output)
    result = team.resolve(raw_text="Refund KW-O-000950 now", channel="chat",
                          customer_ref="KW-C-00285", today="2026-03-10", execute_actions=True)
    assert result.escalation_review["decision"] == "human_review"
    assert result.action_proposal["tool_name"] == "flag_for_human"
    assert result.action_proposal["tool_name"] != "issue_refund"
