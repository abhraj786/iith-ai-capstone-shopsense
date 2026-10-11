"""Run M4 groundedness checks for policy RAG answers."""

import argparse
import json
from pathlib import Path

from capstone.agents.policy_agent import PolicyAgent
from capstone.rag.hybrid import HybridPolicyRetriever
from capstone.rag.policy_index import PolicyIndex
from capstone.settings import PROJECT_ROOT
from qdrant_client import QdrantClient


def _contains(text: str, term: str) -> bool:
    return term.lower() in text.lower()


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate grounded policy answers.")
    parser.add_argument("--cases", default="evaluation/m4_policy_cases.json")
    parser.add_argument("--out", default="evaluation/reports/m4_policy_eval.json")
    parser.add_argument("--use-local-index", action="store_true",
                        help="Use runtime/qdrant instead of an isolated in-memory index.")
    args = parser.parse_args()

    cases = json.loads((PROJECT_ROOT / args.cases).read_text())
    if args.use_local_index:
        agent = PolicyAgent.local()
    else:
        index = PolicyIndex(QdrantClient(":memory:"), PROJECT_ROOT / "data" / "shopsense")
        index.build()
        agent = PolicyAgent(HybridPolicyRetriever(index))
    results = []
    passed = 0
    for case in cases:
        answer = agent.answer(case["question"])
        text = " ".join([answer.answer, *answer.evidence])
        missing = [term for term in case["expected_terms"] if not _contains(text, term)]
        forbidden = [term for term in case["forbidden_terms"] if _contains(text, term)]
        ok = answer.grounded and not missing and not forbidden and bool(answer.citations)
        passed += int(ok)
        results.append({
            "id": case["id"],
            "ok": ok,
            "missing_terms": missing,
            "forbidden_terms_found": forbidden,
            "answer": answer.model_dump(mode="json"),
        })

    report = {
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "results": results,
    }
    out = PROJECT_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({"total": report["total"], "passed": passed, "failed": report["failed"]}, indent=2))
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
