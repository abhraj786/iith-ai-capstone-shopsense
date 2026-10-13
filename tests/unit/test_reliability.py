"""M7 tracing and reliability tests."""

import json
from types import SimpleNamespace

from qdrant_client import QdrantClient

from capstone.agents.policy_agent import PolicyAgent
from capstone.llm.client import LLMClient
from capstone.memory.store import CustomerMemoryStore
from capstone.observability.tracing import TraceRecorder
from capstone.rag.hybrid import HybridPolicyRetriever
from capstone.rag.policy_index import PolicyIndex
from capstone.reliability.tools import CircuitBreaker, ReliableToolGateway, RetryPolicy
from capstone.settings import Settings, get_settings
from capstone.team.multi_agent import MultiAgentTeam
from capstone.tools.repository import Repository


class FlakyGateway:
    def __init__(self, failures_before_success: int = 1):
        self.calls = 0
        self.failures_before_success = failures_before_success

    def track_shipment(self, customer_ref, order_ref):
        self.calls += 1
        if self.calls <= self.failures_before_success:
            return {"ok": False, "error": {"error": "timeout", "message": "temporary outage"}}
        return {"ok": True, "result": {"order_ref": order_ref}, "transport": "fake"}


class DownGateway:
    def track_shipment(self, customer_ref, order_ref):
        return {"ok": False, "error": {"error": "timeout", "message": "order API down"}}


def _client(output: dict) -> LLMClient:
    def completion(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(output)))]
        )

    return LLMClient(Settings(llm_max_retries=0), completion=completion)


def _policy_agent():
    index = PolicyIndex(QdrantClient(":memory:"), get_settings().data_root / get_settings().domain)
    index.build()
    return index, PolicyAgent(HybridPolicyRetriever(index))


def _track_ticket():
    return {
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


def test_reliable_gateway_retries_transient_tool_failure():
    gateway = FlakyGateway(failures_before_success=1)
    reliable = ReliableToolGateway(
        gateway,
        retry_policy=RetryPolicy(attempts=2, backoff_s=0),
        circuit_breaker=CircuitBreaker(failure_threshold=2),
    )

    result = reliable.track_shipment("KW-C-00285", "KW-O-000950")

    assert result["ok"]
    assert result["reliability"]["attempts"] == 2
    assert gateway.calls == 2


def test_reliable_gateway_opens_circuit_after_repeated_failures():
    reliable = ReliableToolGateway(
        DownGateway(),
        retry_policy=RetryPolicy(attempts=1, backoff_s=0),
        circuit_breaker=CircuitBreaker(failure_threshold=1, cooldown_s=60),
    )

    first = reliable.track_shipment("KW-C-00285", "KW-O-000950")
    second = reliable.track_shipment("KW-C-00285", "KW-O-000950")

    assert not first["ok"]
    assert first["reliability"]["fallback"] == "human_queue"
    assert not second["ok"]
    assert second["error"]["error"] == "circuit_open"


def test_team_falls_back_to_human_queue_and_writes_trace(tmp_path):
    index, policy_agent = _policy_agent()
    team = MultiAgentTeam(
        client=_client(_track_ticket()),
        repo=Repository(get_settings().seed_dir, tmp_path / "state"),
        memory_store=CustomerMemoryStore(tmp_path / "memory"),
        policy_index=index,
        policy_agent=policy_agent,
        tool_gateway=ReliableToolGateway(
            DownGateway(),
            retry_policy=RetryPolicy(attempts=1, backoff_s=0),
            circuit_breaker=CircuitBreaker(failure_threshold=1),
        ),
        reliable_tools=False,
        tracer=TraceRecorder(tmp_path / "traces"),
    )

    result = team.resolve(
        raw_text="Where is order KW-O-000950?",
        channel="chat",
        customer_ref="KW-C-00285",
        today="2026-03-10",
    )

    assert result.escalation_review["decision"] == "human_review"
    assert result.action_proposal["tool_name"] == "flag_for_human"
    assert result.action_proposal["tool_result"]["routes_to"] == "agent"
    assert result.trace["trace_id"]
    assert (tmp_path / "traces" / f"{result.trace['trace_id']}.jsonl").exists()

