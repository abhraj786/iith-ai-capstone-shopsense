"""M5 LangGraph workflow tests."""

import json
from datetime import date
from types import SimpleNamespace

from qdrant_client import QdrantClient

from capstone.agents.policy_agent import PolicyAgent
from capstone.llm.client import LLMClient
from capstone.memory.store import CustomerMemoryStore
from capstone.rag.hybrid import HybridPolicyRetriever
from capstone.rag.policy_index import PolicyIndex
from capstone.settings import PROJECT_ROOT, Settings, get_settings
from capstone.tools import lookups
from capstone.tools.calculators import delivered_on
from capstone.tools.repository import Repository
from capstone.workflow.graph import WorkflowCheckpointStore, WorkflowDeps, run_ticket_workflow


def _client(output: dict) -> LLMClient:
    def completion(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(output)))]
        )

    return LLMClient(Settings(llm_max_retries=0), completion=completion)


def _deps(tmp_path, output: dict) -> tuple[WorkflowDeps, Repository]:
    repo = Repository(get_settings().seed_dir, tmp_path / "state")
    policy_index = PolicyIndex(QdrantClient(":memory:"), PROJECT_ROOT / "data" / "shopsense")
    policy_index.build()
    deps = WorkflowDeps(
        client=_client(output),
        repo=repo,
        memory_store=CustomerMemoryStore(tmp_path / "memory"),
        policy_index=policy_index,
        policy_agent=PolicyAgent(HybridPolicyRetriever(policy_index)),
        checkpointer=WorkflowCheckpointStore(tmp_path / "checkpoints"),
    )
    return deps, repo


def _delivered_late_order(repo: Repository, max_value: int = 2000) -> dict:
    refunded = {r["order_ref"] for r in repo.rows("refunds") + repo.rows("replacements")}
    for raw in repo.rows("orders"):
        order = lookups.get_order(repo, raw["customer_ref"], raw["order_ref"])
        customer = lookups.get_customer(repo, raw["customer_ref"])
        eligible = (
            raw["status"] == "delivered"
            and delivered_on(raw) is not None
            and raw["order_ref"] not in refunded
            and customer.get("automated_refunds_allowed") != "False"
            and customer.get("serial_refund_requester") != "True"
            and customer.get("flagged_for_abuse") != "True"
            and float(raw["order_value_inr"]) <= max_value
            and delivered_on(raw) <= date(2026, 3, 10)
        )
        if eligible and lookups.get_order(repo, raw["customer_ref"], raw["order_ref"]):
            policy = repo.get("orders", order_ref=raw["order_ref"])
            if int(policy["actual_delivery_days"]) <= int(policy["delivery_promise_days"]):
                continue
            return order
    raise AssertionError("No eligible delivered late low-value order found")


def test_m5_auto_resolves_low_risk_refund_with_checkpoints(tmp_path):
    deps, repo = _deps(tmp_path, {})
    order = _delivered_late_order(repo)
    output = {
        "issue_type": "delivery_delay",
        "order_ref": order["order_ref"],
        "sentiment": "calm",
        "urgency": "normal",
        "claimed_amount_inr": float(order["order_value_inr"]),
        "contact_number": 1,
        "escalation_signals": [],
        "prompt_injection_suspected": False,
        "missing_fields": [],
        "summary": "Customer requests a refund because the delivery was late.",
    }
    deps.client = _client(output)

    result = run_ticket_workflow(
        raw_text=f"Please refund order {order['order_ref']} because the delivery was late.",
        channel="email",
        customer_ref=order["customer_ref"],
        today="2026-03-10",
        run_id="auto-refund",
        execute_actions=True,
        deps=deps,
    )

    assert result["status"] == "auto_resolved_executed"
    assert result["route"] == "auto_execute"
    assert result["action_proposal"]["executed"]
    assert result["action_proposal"]["tool_result"]["status"] == "approved"
    assert len(result["checkpoints"]) >= 5
    assert (tmp_path / "checkpoints" / "auto-refund").exists()


def test_m5_interrupts_angry_legal_ticket_for_human(tmp_path):
    output = {
        "issue_type": "refund_request",
        "order_ref": "KW-O-000950",
        "sentiment": "angry",
        "urgency": "critical",
        "claimed_amount_inr": 6499,
        "contact_number": 2,
        "escalation_signals": ["legal_or_regulatory", "angry_or_abusive"],
        "prompt_injection_suspected": False,
        "missing_fields": [],
        "summary": "Customer demands a refund and threatens legal action.",
    }
    deps, _ = _deps(tmp_path, output)

    result = run_ticket_workflow(
        raw_text="Refund KW-O-000950 or I will file a legal complaint.",
        channel="email",
        customer_ref="KW-C-00285",
        today="2026-03-10",
        run_id="legal-human",
        execute_actions=True,
        deps=deps,
    )

    assert result["status"] == "human_approval_required"
    assert result["route"] == "human_interrupt"
    assert result["action_proposal"]["recommended_action"] == "human_review"
    assert result["action_proposal"]["tool_args"]["trigger"] == "legal_or_regulatory"
    assert result["memory_context"]["ticket_count"] == 1
    assert result["policy_answer"]["grounded"]
    assert len(result["checkpoints"]) >= 5
