"""M8 component-level golden evaluation: tool use, retrieval, planning and final answer.

Deterministic scores always run. `--judge` adds the in-repo LLM judge (faithfulness for answers, context
relevance for retrieval) and the list of rows where the two disagree by more than 0.4.
`--langfuse` also runs the items as a Langfuse experiment (sequential) with the scores attached.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import date
from pathlib import Path

from qdrant_client import QdrantClient

from capstone.agents.action_agent import plan_action
from capstone.agents.policy_agent import PolicyAgent
from capstone.eval_scorers import DETERMINISTIC, disagreements, judge_context_relevance, judge_faithfulness, metric_averages
from capstone.guardrails import apply_guardrails, safe_policy_answer
from capstone.rag.hybrid import HybridPolicyRetriever
from capstone.rag.policy_index import PolicyIndex
from capstone.schemas.intake import SupportTicket
from capstone.settings import PROJECT_ROOT, get_settings
from capstone.tools.lookups import order_category
from capstone.tools.repository import Repository

DATA = PROJECT_ROOT / "data/shopsense/eval"


def run_pipeline(case: dict, repo: Repository, policy_agent: PolicyAgent) -> dict:
    """Stored ticket -> policy RAG -> action plan -> guardrails; returns what each component produced."""
    from scripts.run_m8_golden_eval import _policy_query

    ticket = SupportTicket.model_validate(case["support_ticket"])
    question = _policy_query(ticket)
    answer = policy_agent.answer(question, category=order_category(repo, case["customer_ref"], ticket.order_ref))
    proposal = plan_action(repo, ticket, case["customer_ref"], date.fromisoformat(case["today"]), execute=False)
    proposal, guardrails = apply_guardrails(ticket, proposal, answer)
    shown = safe_policy_answer(answer.model_dump(mode="json"), guardrails)
    return {
        "question": question, "tool_name": proposal.tool_name,
        "recommended_action": proposal.recommended_action.value,
        "answer": shown["answer"], "evidence": answer.evidence,
        "cited_docs": sorted({c.document_slug for c in answer.citations}),
    }


def build(args) -> dict:
    cases = {c["case_id"]: c for c in json.loads((DATA / "golden_m8_tickets.json").read_text())}
    items = json.loads(args.items.read_text())
    settings = get_settings()
    index = PolicyIndex(QdrantClient(":memory:"), PROJECT_ROOT / settings.data_root / settings.domain)
    index.build(recreate=False)
    policy_agent = PolicyAgent(HybridPolicyRetriever(index))
    client = None
    if args.judge:
        from capstone.llm.client import LLMClient
        client = LLMClient()

    rows, actuals = [], {}
    with tempfile.TemporaryDirectory(prefix="shopsense-m8-comp-") as tmp:
        repo = Repository(settings.seed_dir, Path(tmp) / "state")
        for item in items:
            case = cases[item["case_id"]]
            actual = actuals.setdefault(item["case_id"], run_pipeline(case, repo, policy_agent))
            row = {"item_id": item["item_id"], "component": item["component"], "case_id": item["case_id"],
                   "deterministic": DETERMINISTIC[item["component"]](item["expected"], actual), "judge": None}
            if client and item["component"] in ("retrieval", "final_answer"):
                if item["component"] == "retrieval":
                    verdict = judge_context_relevance(client, actual["question"], actual["evidence"])
                else:
                    verdict = judge_faithfulness(client, actual["question"], actual["answer"], actual["evidence"])
                row["judge"], row["judge_reason"] = verdict.score, verdict.reason
            rows.append(row)

    report = {
        "total": len(rows),
        "deterministic_average": metric_averages(rows, "deterministic"),
        "judge_average": metric_averages(rows, "judge"),
        "judge": "in-repo LLM judge on LLMClient (not Ragas/DeepEval/TruLens)" if client else None,
        "disagreements_over_0.4": disagreements(rows),
        "rows": rows,
    }
    if args.langfuse:
        report["langfuse_experiment"] = _langfuse_experiment(items, cases, repo_state=settings, policy_agent=policy_agent)
    return report


def _langfuse_experiment(items: list[dict], cases: dict, *, repo_state, policy_agent) -> dict:
    from langfuse import Evaluation, Langfuse

    kwargs = {"public_key": repo_state.langfuse_public_key or os.getenv("LANGFUSE_PUBLIC_KEY"),
              "secret_key": repo_state.langfuse_secret_key or os.getenv("LANGFUSE_SECRET_KEY")}
    host = repo_state.langfuse_host or os.getenv("LANGFUSE_HOST")
    if host:
        kwargs["host"] = host
    lf = Langfuse(**kwargs)
    tmp = tempfile.TemporaryDirectory(prefix="shopsense-m8-lf-")
    repo = Repository(repo_state.seed_dir, Path(tmp.name) / "state")

    def task(*, item, **_):
        return run_pipeline(cases[item["input"]["case_id"]], repo, policy_agent)

    def evaluator(*, input, output, expected_output, **_):
        value = DETERMINISTIC[input["component"]](expected_output, output)
        return Evaluation(name=f"{input['component']}_score", value=value, comment=input["item_id"])

    result = lf.run_experiment(
        name="shopsense-m8-component-golden", description="20 golden items: tool use, retrieval, planning, final answer",
        data=[{"input": {k: i[k] for k in ("item_id", "component", "case_id")}, "expected_output": i["expected"]} for i in items],
        task=task, evaluators=[evaluator], max_concurrency=1)  # sequential: no rate-limit bursts
    lf.flush()
    tmp.cleanup()
    return {"run_name": getattr(result, "run_name", None), "items": len(items),
            "dataset_run_url": getattr(result, "dataset_run_url", None)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", type=Path, default=DATA / "golden_m8_components.json")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "evaluation/reports/m8_component_eval.json")
    parser.add_argument("--judge", action="store_true", help="add the LLM judge (needs the model API)")
    parser.add_argument("--langfuse", action="store_true", help="also run as a Langfuse experiment")
    args = parser.parse_args()
    report = build(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("total", "deterministic_average", "judge_average")}, indent=2))
    for row in report["disagreements_over_0.4"]:
        print("DISAGREE", row["item_id"], row["case_id"], row["deterministic"], row["judge"], row.get("judge_reason"))


if __name__ == "__main__":
    main()
