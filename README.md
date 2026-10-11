# IITH AI Capstone: ShopSense

ShopSense customer-care and order-operations capstone for the IIT Hyderabad Applied AI program.

This repository currently implements **M1: Intake Parsing**, **M2: Safe Action Planning**, **M3: Memory + Policy Index**, **M4: Grounded Policy RAG**, and **M5: LangGraph Workflow**. M1 converts raw customer support messages into validated structured tickets. M2 takes those tickets and proposes the next operational action through deterministic policy tools. M3 persists per-customer interaction memory and builds a Qdrant index over ShopSense policy documents. M4 answers policy questions using hybrid retrieval, reranking, citations, and groundedness checks. M5 connects those modules into a checkpointed workflow with human-approval interrupts.

## What Is Included

- ShopSense generated intake records under `data/shopsense/intake/`
- ShopSense mock policy/API tables under `data/shopsense/mock_api/`
- M1 intake prompt under `prompts/intake.md`
- Pydantic ticket schema under `src/capstone/schemas/intake.py`
- LiteLLM structured-output client under `src/capstone/llm/client.py`
- Intake parser under `src/capstone/agents/intake_agent.py`
- M2 action planner under `src/capstone/agents/action_agent.py`
- Deterministic lookup, policy, and action tools under `src/capstone/tools/`
- M3 per-customer memory store under `src/capstone/memory/store.py`
- M3 Qdrant policy index under `src/capstone/rag/policy_index.py`
- M4 policy RAG agent under `src/capstone/agents/policy_agent.py`
- M4 hybrid retrieval under `src/capstone/rag/hybrid.py`
- M5 LangGraph workflow under `src/capstone/workflow/graph.py`
- M1 evaluation script under `scripts/run_intake_eval.py`
- Unit tests under `tests/unit/`
- Latest committed M1 report under `evaluation/reports/m1_holdout_n60_v4.json`

Secrets, virtual environments, caches, and runtime state are intentionally excluded from Git.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

For live LLM evaluation, copy `.env.example` to `.env` and add your provider key:

```bash
cp .env.example .env
```

Do not commit `.env`.

## Run Tests

```bash
python -m pytest tests/unit
```

Expected current result:

```text
43 passed
```

## Run Local Workbench UI

Use the workbench to test M1 and M2 together from a browser:

```bash
python -m capstone.workbench.app --port 8765
```

Then open:

```text
http://127.0.0.1:8765
```

The UI supports full M1+M2 runs and M2-only runs from pasted `SupportTicket` JSON. Full M1+M2 runs require the same `.env` model configuration used by the M1 evaluation script.

Build or refresh the M3/M4 policy index directly:

```bash
python scripts/build_policy_index.py
```

By default this uses local persistent Qdrant under `runtime/qdrant`, so an evaluator can
run the project without private credentials. To use Qdrant Cloud, add the same variables
used in the course Colab to `.env`:

```bash
QDRANT_URL=...
QDRANT_API_KEY=...
QDRANT_COLLECTION=shopsense_policy_m3
```

When cloud settings are present, the app tries Qdrant Cloud first. If the cloud endpoint is
unavailable, it falls back to local Qdrant so demos and evaluations can continue.

Run M4 groundedness evaluation:

```bash
python scripts/run_policy_eval.py
```

To run the evaluation against the configured persistent index instead of the isolated
in-memory test index:

```bash
python scripts/run_policy_eval.py --use-configured-index
```

## Run M1 Evaluation

The evaluation sends only `raw_text` and `channel` to the LLM. Ground-truth labels remain local and are used only after parsing to score the output.

```bash
python scripts/run_intake_eval.py --n 60 --offset 60 --out evaluation/reports/m1_holdout_n60_v4.json
```

Latest committed report:

```text
parsed: 60
parse_failures: 0
intent_accuracy: 0.717
sentiment_accuracy: 0.783
escalation_signal_precision: 0.896
escalation_signal_recall: 0.822
```

## M1 Design

The LLM handles language understanding. Python enforces deterministic rules.

- The model produces JSON matching `SupportTicket`.
- Pydantic validates the schema.
- Order references are accepted only if they appear in the customer text.
- `refund_above_auto_cap` and `repeat_contact` are removed from model output and recomputed from policy thresholds in code.
- Prompt-injection attempts are treated as customer data, not instructions.

This keeps exact policy decisions out of the LLM and makes the intake output safer for later milestones.

## M2 Design

M2 starts with a safe action boundary. The LLM does not approve refunds or mutate state.

- `plan_action(...)` accepts a validated `SupportTicket`, customer reference, and policy date.
- Read-only lookups can return tracking details during planning.
- Refunds, replacements, and human queue entries are proposal-only unless `execute=True`.
- Refund eligibility, amounts, approval tiers, idempotency, and customer-scoped order access are enforced in Python tools.
- Risk signals such as legal threats, repeat contact, account restrictions, and over-cap refunds route to a human queue.

## M3 Design

M3 adds local persistence and policy retrieval foundations.

- `CustomerMemoryStore` stores one JSON file per customer under runtime memory.
- Memory captures semantic preferences, episodic ticket/action history, procedural policy/tool boundaries, and a deterministic rolling summary for later workflow context.
- `PolicyIndex` builds a Qdrant collection from the markdown policy corpus.
- Qdrant Cloud is used when `QDRANT_URL` and `QDRANT_API_KEY` are configured and reachable; otherwise the same code falls back to local persistent Qdrant for reproducible evaluation.
- Embeddings are deterministic and local so tests do not require an external embedding model.
- M4 can replace this with hybrid search/reranking while keeping the Qdrant collection boundary.

## M4 Design

M4 turns policy retrieval into grounded policy answers.

- Hybrid retrieval combines Qdrant vector hits with deterministic keyword retrieval.
- Reranking boosts exact policy/category matches before answer generation.
- `PolicyAgent` answers only from retrieved evidence and returns citations.
- Groundedness checks reject unsupported numeric claims, preventing invented return windows or refund amounts.
- `evaluation/m4_policy_cases.json` covers category windows, groceries, legal routing, and the automated refund cap.

## M5 Design

M5 connects the earlier modules into one checkpointed LangGraph workflow.

- Nodes run triage, memory update, policy check, action planning, and final routing.
- Low-risk cases can auto-execute deterministic M2 tools when `execute_actions=True`.
- Angry, distressed, critical, legal, safety, over-cap, and policy-restricted cases pause with a LangGraph `interrupt()`.
- Human review resumes through `Command(resume=...)`, and approved cases can execute the queued M2 action.
- LangGraph state is durably checkpointed in SQLite under `runtime/workflow_checkpoints.sqlite`.
- Each node also writes an inspectable JSON audit snapshot under `runtime/workflow_checkpoints/<run_id>/`.
- Unit tests cover auto-resolution, human interrupt, and resume paths without calling a live LLM.
