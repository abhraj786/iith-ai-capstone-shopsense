# ShopSense Architecture Review

## System overview

ShopSense is a customer-care and order-operations assistant for a retail platform. A customer message goes in; the system parses it into a validated `SupportTicket`, looks up the customer's order, retrieves the matching policy, plans an action (track, replace, refund, ask for info) and either executes it or hands it to a human. The job it has to get right is **never taking a money-moving or policy-sensitive action it should not**. Refunds above the Rs 2000 cap, angry or legal customers, product-safety reports and prompt-injection attempts all go to human review, whatever the LLM says.

## Components & data flow

`intake -> memory -> tools (MCP) + policy RAG -> action planner -> guardrails -> auto-execute or human interrupt`

| Component | What it does | Failure mode if this breaks |
|---|---|---|
| Intake agent | LLM (LiteLLM) fills a Pydantic `SupportTicket`; a regex screen also flags prompt injection (English, Hinglish, delimiter breakout) | Wrong intent or order, or a missed injection, so the wrong tool runs |
| Memory | One JSON file per customer: every ticket is kept; the newest 5 stay verbatim and older ones are condensed by the LLM into a summary merged with the previous one. Memory also counts earlier contacts on the same order and issue (per date and channel), so the repeat-contact flag (3 or more) works even when the customer does not say it. Lasting facts the customer states (delivery instructions, allergies) are saved as `known_facts` (max 3 per ticket, 20 per customer, never from injection-flagged messages) and survive summarizing | A planted fact is lost in summarizing (tested by `scripts/run_memory_recall_check.py`), or a re-sent message escalates itself |
| Tools (MCP server/client) | Deterministic customer-scoped lookups; the refund amount is computed from the order value, not the claimed amount | Another customer's order is exposed, or a wrong refund figure |
| Policy RAG | Gemini `gemini-embedding-001` (768d) in Qdrant, plus BM25 score fusion and an optional cross-encoder; the order category excludes the other categories' addenda | The answer cites the wrong category window (for example groceries vs apparel) |
| Action planner and guardrails | Deterministic rules, cap and escalation signals (angry, legal, safety, above cap, repeat, human requested, delivery dispute) | An unsafe auto-action. This is the most critical component. |
| Multi-agent team (M6) | Triage, Supervisor, Memory, Policy RAG, Order-Actions and Escalation Reviewer share a case board with per-agent write scopes. The Supervisor (LLM) sees only the structured ticket and picks `full`, `fast_track` or `escalate_now` from a menu that code limits by ticket risk; the Reviewer re-checks the plan before any write and can only send it to a human; an ungrounded policy answer is sent back for a wider lookup at most twice | A fooled router skips a check (prevented: risky tickets can only get `full`, reviewer and write step run on every route), or a stage overwrites another's work (prevented by `PermissionError`) |
| LangGraph workflow | Checkpointed in SQLite, with an interrupt before human review | Lost state or a bypassed approval |
| Observability and reliability | LangFuse traces; tool calls get retry, circuit breaker and human-queue fallback | Failures that nobody can see |

## Evaluation results summary

**M4 retrieval** (`scripts/run_retrieval_eval.py`, 24 questions, Gemini embeddings):

| Config | hit@1 | recall@3 | MRR |
|---|---|---|---|
| dense only | 0.917 | 0.979 | 0.951 |
| BM25 only | 0.542 | - | - |
| hybrid fused | 0.875 | 1.000 | 0.931 |
| hybrid + rerank | 0.875 | 1.000 | 0.924 |

Answer checks pass 22/24 without the order category and 24/24 with it. The two misses omit the figure; none gives a wrong number. Dense-only has a slightly higher hit@1; hybrid is kept because it reaches recall@3 of 1.0, and the answer step reads the top 3 or more. BM25 and the reranker are weighted lightly on purpose: Reciprocal Rank Fusion pushed the wrong documents up on this small corpus.

**M8 golden set** (`scripts/run_m8_golden_eval.py`, 20 cases over 5 customers): 20/20 on stored tickets and 20/20 with live LLM parsing (`--live`). It covers 5 injection variants, over-cap, angry, legal, safety, repeat, cross-customer and nonexistent orders, and out-of-window returns.

**M8 component golden set** (`scripts/run_m8_component_eval.py`, 20 items: 5 each for tool use, retrieval, planning and final answer). Deterministic scorers: tool match, document and keyword hit, action match, answer keywords. Average 1.0 on all four components with real embeddings. An LLM judge (an in-repo judge on the project LLM client, not Ragas, DeepEval or TruLens) scored context relevance on retrieval and faithfulness on answers: faithfulness 1.0 on 5/5, context relevance 0.6 on average. It disagreed with the keyword scorer by more than 0.4 on two items: the product-safety case (the retrieved text is about transfer SLAs, not the sparking and burning report) and the double-charge case (the retrieved text is about refund calculations, not a duplicate payment). The keyword check passed both because the expected words appeared; the judge is right that the retrieval is weak there. The golden label for one answer item first expected the word "human" in a policy answer, which is the planner's job, so the label was corrected. The same 20 items also run as a sequential Langfuse experiment (`--langfuse`).

**M1 intake holdout** (60 records):

| Model | Intent acc. | Sentiment acc. | Escalation recall | Escalation precision |
|---|---|---|---|---|
| gemini-flash-lite | 0.717 | 0.783 | 0.822 | 0.896 |
| groq gpt-oss-20b | 0.617 | 0.700 | 0.712 | 0.945 |

Both are below a 0.8 intent target. The labels come from noisy Twitter-style data and the two models disagree with the labels in different places. Gemini is the better default for escalation recall, which is the metric that matters for safety. The deterministic guardrails do not depend on intent accuracy for the refund cap.

**Changes made in response:** the first retrieval run used hash vectors, so I moved to real embeddings. Wrong-category answers led to the order-category filter. A Hinglish injection slipped past the LLM flag, so I added the regex screen. The old golden set was narrow, so I rebuilt it.

## Guardrails & safety

Covered:
- Pydantic schema validation of every ticket.
- Prompt-injection detection by regex and by the LLM flag. A flagged ticket always goes to a human.
- The Rs 2000 auto-refund cap, enforced in code, with the amount computed from the order value.
- Retrieved policy text is scanned too: the policy agent drops instruction-like sentences, and the guardrail layer re-checks the answer and evidence (`retrieved_content_injection_blocked`).
- Customer-scoped lookups.
- Human interrupt for the seven escalation signals.

Out of scope in this version:
- No PII redaction in traces.
- The injection regex is a pattern list and can be evaded by novel phrasings (the LLM flag is the second layer).
- No auth on `/chat`.
- No rate limiting.

## Known limitations

- Intent accuracy is about 0.62-0.72 on the noisy holdout.
- The corpus is small (3 policy documents plus category addenda), so retrieval numbers are optimistic.
- Answer extraction is sentence-based, not generative.
- `/chat` returns 200 with a human-review status on a guardrail block; the lab example returns 422. This is deliberate, because a blocked ticket is a valid outcome, not a client error.
- The golden set uses a fixed "today" date.
- The Docker image and a public endpoint were not exercised.

## Deployment notes

- Secrets live in a git-ignored `.env`; `.env.example` lists the variables. Never commit keys.
- Embeddings fall back to the hash backend when no Gemini key is set (`CAPSTONE_EMBEDDINGS=hash`), so tests run offline. Embeddings are cached in `runtime/embedding_cache.json`.
- LLM calls: schema-invalid output is re-asked up to 2 times with the error; 429 rate limits wait and retry (8s, doubling, up to 4 retries); LiteLLM adds 2 network retries; 60s timeout. There is no model-to-model fallback; if the LLM stays down the call raises `LLMError`.
- Tool calls (M7): MCP first with a visible in-process failover; 2 attempts with backoff, a per-tool circuit breaker (closed, open, half-open with one trial call), and a human-queue fallback when it opens. If the LLM is down, /chat hands the case to a human.
- Tracing (M7): Triage and Supervisor are Langfuse generation spans with tokens and cost; Langfuse events are batched in the background.
- Embeddings: retry with backoff, disk cache, and a hash fallback when no key is set.
- Logging: LangFuse traces plus local JSONL traces in `runtime/`.
- Rollback: the Qdrant collection name carries the backend suffix (`_gemini`), so the old collection stays intact. Redeploy the previous git tag.
- Container: `Dockerfile` (python 3.12-slim, editable install, non-root user, health check) and `docker-compose.yml` (loads `.env`, mounts `runtime/`). The image was written but not built here, because Docker is not installed on the development machine.
- Public endpoint: run `uvicorn capstone.api:app --port 8000`, then `ngrok http 8000`. The Postman collection `docs/postman/shopsense_chat.postman_collection.json` (health, tickets A, B, C and an empty-text 422) was run against a local server; it was not run through a tunnel.
- Status codes: a malformed request returns 422. A guardrail block returns 200 with `requires_human` and the findings, because a refused-for-safety ticket is a successful hand-over to a person, not a client error.
- Deferred: auth and rate limiting on the public endpoint.
