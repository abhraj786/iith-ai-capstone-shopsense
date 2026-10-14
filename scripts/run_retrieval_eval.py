"""M4 retrieval evaluation: dense vs keyword vs hybrid on a golden question set.

Reports hit@1, precision@3, recall@3 and MRR at document level, plus answer-level checks
(expected figure present, other-category windows absent). Category addenda deliberately
conflict with the baseline policy, so retrieving the wrong category document fails here.
"""

import argparse
import json

from qdrant_client import QdrantClient

from capstone.agents.policy_agent import PolicyAgent
from capstone.rag.hybrid import HybridPolicyRetriever
from capstone.rag.policy_index import PolicyIndex
from capstone.settings import PROJECT_ROOT


def _slugs(hits, k):
    seen: list[str] = []
    for hit in hits:
        if hit.document_slug not in seen:
            seen.append(hit.document_slug)
    return seen[:k]


def _metrics(rows, k=3):
    n = len(rows)
    return {
        "hit@1": round(sum(r["ranked"][:1] and r["ranked"][0] in r["relevant"] for r in rows) / n, 3),
        f"precision@{k}": round(sum(len(set(r["ranked"][:k]) & set(r["relevant"])) / k for r in rows) / n, 3),
        f"recall@{k}": round(sum(len(set(r["ranked"][:k]) & set(r["relevant"])) / len(r["relevant"]) for r in rows) / n, 3),
        "mrr": round(sum(next((1 / (i + 1) for i, s in enumerate(r["ranked"]) if s in r["relevant"]), 0.0) for r in rows) / n, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare retrieval variants on the M4 golden set.")
    parser.add_argument("--cases", default="evaluation/m4_retrieval_golden.json")
    parser.add_argument("--out", default="evaluation/reports/m4_retrieval_eval.json")
    parser.add_argument("--configured-index", action="store_true", help="Use Qdrant Cloud when configured.")
    args = parser.parse_args()

    cases = json.loads((PROJECT_ROOT / args.cases).read_text())
    if args.configured_index:
        index = PolicyIndex.from_settings()
    else:
        index = PolicyIndex(QdrantClient(":memory:"), PROJECT_ROOT / "data" / "shopsense")
        index.build()
    retriever = HybridPolicyRetriever(index)
    reranker = HybridPolicyRetriever(index, rerank=True)
    variants = {
        "dense_only": lambda q: index.search(q, limit=12),
        "bm25_only": lambda q: retriever.keyword_search(q, limit=12),
        "hybrid_fused": lambda q: retriever.fused_search(q, limit=12),
        "hybrid_fused_rerank": lambda q: reranker.retrieve(q, limit=12),
    }
    from capstone.rag import embeddings
    report: dict = {"total": len(cases), "embedding_backend": embeddings.backend_name(), "variants": {}}
    for name, search in variants.items():
        rows = [{"id": c["id"], "relevant": c["relevant"], "ranked": _slugs(search(c["question"]), 5)} for c in cases]
        report["variants"][name] = {**_metrics(rows), "misses_at_1": [r["id"] for r in rows if r["ranked"][:1] and r["ranked"][0] not in r["relevant"]]}

    agent = PolicyAgent(reranker)

    def _answers(use_category: bool) -> dict:
        rows = []
        for c in cases:
            ans = agent.answer(c["question"], category=c.get("order_category") if use_category else None)
            text = " ".join([ans.answer, *ans.evidence]).lower()
            missing = [t for t in c["expected_terms"] if t.lower() not in text]
            forbidden = [t for t in c["forbidden_terms"] if t.lower() in text]
            rows.append({"id": c["id"], "ok": ans.grounded and not missing and not forbidden,
                         "missing_terms": missing, "forbidden_found": forbidden})
        return {"passed": sum(r["ok"] for r in rows), "total": len(rows), "failures": [r for r in rows if not r["ok"]]}

    report["answers_without_order_category"] = _answers(False)
    report["answers_with_order_category"] = _answers(True)
    out = PROJECT_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({"embedding_backend": report["embedding_backend"], "variants": report["variants"],
                      **{k: {x: report[k][x] for x in ("passed", "total")} for k in
                         ("answers_without_order_category", "answers_with_order_category")}}, indent=2))
    for key in ("answers_without_order_category", "answers_with_order_category"):
        for r in report[key]["failures"]:
            print("FAIL", key, r)


if __name__ == "__main__":
    main()
