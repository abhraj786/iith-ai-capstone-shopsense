"""Run the M8 golden ticket guardrail evaluation."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import date
from pathlib import Path

from qdrant_client import QdrantClient

from capstone.agents.action_agent import plan_action
from capstone.agents.intake_agent import parse_ticket
from capstone.llm.client import LLMClient
from capstone.agents.policy_agent import PolicyAgent
from capstone.guardrails import apply_guardrails
from capstone.rag.hybrid import HybridPolicyRetriever
from capstone.rag.policy_index import PolicyIndex
from capstone.schemas.intake import SupportTicket
from capstone.settings import PROJECT_ROOT, get_settings
from capstone.tools.lookups import order_category
from capstone.tools.repository import Repository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=PROJECT_ROOT / "data/shopsense/eval/golden_m8_tickets.json")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--live", action="store_true",
                        help="Parse raw_text with the live LLM (full M1->M8 path) instead of the stored support_ticket.")
    args = parser.parse_args()
    if args.out is None:
        args.out = PROJECT_ROOT / ("evaluation/reports/m8_golden_eval_live.json" if args.live
                                   else "evaluation/reports/m8_golden_eval.json")
    client = LLMClient() if args.live else None

    cases = json.loads(args.cases.read_text())
    settings = get_settings()
    policy_index = PolicyIndex(QdrantClient(":memory:"), PROJECT_ROOT / settings.data_root / settings.domain)
    if not policy_index.client.collection_exists(policy_index.collection_name):
        policy_index.build(recreate=False)
    policy_agent = PolicyAgent(HybridPolicyRetriever(policy_index))

    results = []
    passed = 0
    with tempfile.TemporaryDirectory(prefix="shopsense-m8-eval-") as tmp:
        repo = Repository(settings.seed_dir, Path(tmp) / "state")
        for case in cases:
            result = evaluate_case(case, repo, policy_agent, client)
            results.append(result)
            passed += 1 if result["passed"] else 0

    report = {
        "mode": "live-llm" if args.live else "stored-tickets",
        "model": get_settings().llm_model if args.live else None,
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "accuracy": round(passed / len(results), 3) if results else 0,
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ["total", "passed", "failed", "accuracy"]}, indent=2))


def evaluate_case(case: dict, repo: Repository, policy_agent: PolicyAgent, client: LLMClient | None = None) -> dict:
    if client is not None:
        ticket = parse_ticket(client, case["raw_text"], "chat", auto_refund_cap_inr=2000, repeat_contact_threshold=3)
    else:
        ticket = SupportTicket.model_validate(case["support_ticket"])
    policy_answer = policy_agent.answer(
        _policy_query(ticket), category=order_category(repo, case["customer_ref"], ticket.order_ref))
    proposal = plan_action(repo, ticket, case["customer_ref"], date.fromisoformat(case["today"]), execute=False)
    proposal, guardrails = apply_guardrails(ticket, proposal, policy_answer)

    expect = case.get("expect", {})
    failures: list[str] = []
    if "recommended_action" in expect and proposal.recommended_action.value != expect["recommended_action"]:
        failures.append(f"recommended_action expected {expect['recommended_action']} got {proposal.recommended_action.value}")
    if "requires_human" in expect and proposal.requires_human != expect["requires_human"]:
        failures.append(f"requires_human expected {expect['requires_human']} got {proposal.requires_human}")
    expected_codes = set(expect.get("guardrail_codes", []))
    actual_codes = {finding.code for finding in guardrails.findings}
    missing_codes = expected_codes - actual_codes
    if missing_codes:
        failures.append(f"missing guardrail codes: {sorted(missing_codes)}")
    if expect.get("policy_grounded") is True and not policy_answer.grounded:
        failures.append(f"policy answer not grounded: {policy_answer.unsupported_claims}")
    if proposal.recommended_action.value in expect.get("forbid_actions", []):
        failures.append(f"forbidden action taken: {proposal.recommended_action.value}")
    answer_text = " ".join([policy_answer.answer, *policy_answer.evidence]).lower()
    leaked = [t for t in expect.get("policy_forbidden_terms", []) if t.lower() in answer_text]
    if leaked:
        failures.append(f"policy answer contains forbidden terms: {leaked}")
    if proposal.recommended_action.value == "refund" and proposal.requires_human:
        failures.append("refund action should not be marked both refund and requires_human")

    return {
        "case_id": case["case_id"],
        "passed": not failures,
        "failures": failures,
        "actual": {
            "recommended_action": proposal.recommended_action.value,
            "requires_human": proposal.requires_human,
            "tool_name": proposal.tool_name,
            "guardrail_codes": sorted(actual_codes),
            "policy_grounded": policy_answer.grounded,
        },
    }


def _policy_query(ticket: SupportTicket) -> str:
    return " ".join([
        ticket.issue_type.value,
        ticket.summary,
        " ".join(signal.value for signal in ticket.escalation_signals),
    ]).strip()


if __name__ == "__main__":
    main()
