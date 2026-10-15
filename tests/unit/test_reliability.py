"""M7 tracing and reliability tests."""

import json
from types import SimpleNamespace

from qdrant_client import QdrantClient

from capstone.agents.policy_agent import PolicyAgent
from capstone.llm.client import LLMClient
from capstone.memory.store import CustomerMemoryStore
from capstone.observability.tracing import TraceRecorder, read_trace, summarize_trace
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
    trace_path = tmp_path / "traces" / f"{result.trace['trace_id']}.jsonl"
    assert trace_path.exists()

    events = read_trace(trace_path)
    trace_start = next(event for event in events if event["event"] == "trace_start")
    assert trace_start["session_id"] == result.trace["trace_id"]
    assert trace_start["user_id"] == "KW-C-00285"
    assert "m7" in trace_start["tags"]

    span_starts = [event for event in events if event["event"] == "span_start"]
    tool_span = next(event for event in span_starts if event["name"] == "tool.track_shipment")
    order_agent_span = next(event for event in span_starts if event["name"] == "Order-Actions Agent")
    assert tool_span["parent_span_id"] == order_agent_span["span_id"]

    summary = summarize_trace(trace_path)
    by_role = {row["role"]: row for row in summary}
    assert by_role["tool.track_shipment"]["fallbacks"] == 1
    assert by_role["Order-Actions Agent"]["calls"] == 1



def test_circuit_breaker_half_open_lets_one_trial_and_reopens_on_failure():
    cb = CircuitBreaker(failure_threshold=2, cooldown_s=0.05)
    cb.record_failure("t")
    cb.record_failure("t")
    assert cb.state("t") == "open" and not cb.allow("t")
    import time
    time.sleep(0.06)
    assert cb.state("t") == "half_open"
    assert cb.allow("t") is True      # the single trial
    assert cb.allow("t") is False     # no second call while the trial is in flight
    cb.record_failure("t")            # trial failed: straight back to open
    assert cb.state("t") == "open" and not cb.allow("t")


def test_circuit_breaker_closes_after_one_successful_trial():
    cb = CircuitBreaker(failure_threshold=1, cooldown_s=0.0)
    cb.record_failure("t")
    assert cb.allow("t") is True
    cb.record_success("t")
    assert cb.state("t") == "closed" and cb.allow("t") is True


def test_failover_gateway_uses_python_only_when_mcp_cannot_be_reached():
    from capstone.reliability.tools import FailoverToolGateway

    class Dead:
        def track_shipment(self, c, o):
            raise ConnectionError("mcp server did not start")

    class Refuses:
        def track_shipment(self, c, o):
            return {"ok": False, "error": {"error": "order_not_found"}, "transport": "mcp"}

    local = FlakyGateway(failures_before_success=0)
    down = FailoverToolGateway(Dead(), local)
    result = down.track_shipment("KW-C-1", "KW-O-1")
    assert result["ok"] and result["failover"]["to"] == "python" and down.active == "python"

    refused = FailoverToolGateway(Refuses(), local)
    result = refused.track_shipment("KW-C-1", "KW-O-1")
    assert result["ok"] is False and "failover" not in result and refused.active == "mcp"  # a refusal is not re-run


def test_trace_summary_adds_token_columns_from_llm_usage(tmp_path):
    recorder = TraceRecorder(tmp_path)
    run = recorder.start_trace("t")
    with run.span("Triage Agent") as span:
        span.set_output({"llm_usage": {"calls": 1, "input_tokens": 120, "output_tokens": 30, "cost_usd": 0.0004}})
    path = run.end()["path"]
    row = summarize_trace(path)[0]
    assert (row["input_tokens"], row["output_tokens"], row["cost_usd"]) == (120, 30, 0.0004)


def test_seeded_benchmark_matches_the_lab_numbers():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "run_reliability_benchmark.py"
    spec = importlib.util.spec_from_file_location("bench", path)
    bench = importlib.util.module_from_spec(spec)
    import sys
    sys.modules["bench"] = bench
    spec.loader.exec_module(bench)

    config = bench.FaultConfig(seed=42)
    baseline = bench.run_baseline(config, 200)
    hardened = bench.run_hardened(config, 200)
    assert baseline["ok"] == 114 and baseline["success_rate"] == 0.57
    assert hardened["ok"] == 179 and hardened["fallback"] == 21 and hardened["handled_rate"] == 1.0
    breaker = bench.run_breaker_demo()
    assert breaker == {"calls": 10, "hit_the_dependency": 3, "short_circuited": 7}
