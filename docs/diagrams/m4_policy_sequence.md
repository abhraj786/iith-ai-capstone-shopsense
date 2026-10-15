# M4 Grounded policy RAG: sequence diagram (same customer, same order)

Source: `src/capstone/agents/policy_agent.py`, `src/capstone/rag/hybrid.py`, `src/capstone/rag/policy_index.py`, `src/capstone/guardrails.py`.

Design rule: the answer step uses no LLM. It quotes sentences from the retrieved policy text, so it cannot invent a return window or an amount. A guardrail blocks any answer whose numbers are not in the evidence.

**Sample.** Customer `KW-C-00317`, order `KW-O-000000`, a Home & Kitchen product, damaged on delivery. Real output (Qdrant Cloud, Gemini embeddings):

| Step | Value |
|---|---|
| Query built from the M1 ticket | `damaged_delivery Damaged order, demands refund.` |
| Category (from the order's product, not the LLM) | `Home & Kitchen` |
| Top hits | `category-home-kitchen` #1, #2, #3, #8 and `returns-policy` #3 |
| Answer | "Any Home & Kitchen item delivered damaged ... must be reported ... within **30 days** of the delivery date. Reports exceeding 30 days ... are redirected to the manufacturer warranty process ..." |
| Citation | `category-home-kitchen` #1 (the chunk the sentences came from) |
| grounded | true, no unsupported claims |

Without the category, the same question returned apparel (45 days), furniture, groceries and sports addenda. The category filter is what makes the window 30 days and not 45.

```mermaid
sequenceDiagram
    autonumber
    participant Q as Query (from M1 ticket)
    participant I as Policy index (Qdrant + BM25)
    participant A as Answer agent (no LLM)
    participant G as Guardrail

    Q->>I: "damaged_delivery Damaged order, demands refund." + category Home & Kitchen
    Note over I: Other categories' addenda are excluded first (they contradict each other)
    I->>I: dense Gemini search + small BM25 boost for exact policy terms (+ optional rerank)
    I-->>A: top 5 chunks (category-home-kitchen #1, #2, #3, #8, returns-policy #3)
    Note over A: Anchor on the top document. Keep sentences that match the question; prefer figures
    A->>A: drop a sentence that is only a piece of another one
    A->>A: cite the chunk each sentence came from
    A->>A: grounded check: every number in the answer must appear in the evidence
    A-->>G: PolicyAnswer (answer, evidence, citations, grounded)
    G-->>Q: allowed if grounded. Otherwise policy_fabrication_blocked or unsupported_policy_claim_blocked
```

If no sentence matches, the answer is "I do not have enough policy evidence to answer this." with `grounded=false`.

Honest limit: the answer is extractive, so the number check passes almost by construction. It catches code mistakes. The real protection against inventing a window is that nothing is generated.

Checks: `pytest tests/unit/test_policy_agent.py tests/unit/test_policy_index.py` and `python scripts/run_retrieval_eval.py` (24 questions: hybrid recall@3 1.000, 24 of 24 correct with the order's category, 22 of 24 without).
