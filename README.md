# IITH AI Capstone: ShopSense

ShopSense customer-care and order-operations capstone for the IIT Hyderabad Applied AI program.

This repository currently implements **M1: Intake Parsing**, **M2: Safe Action Planning**, **M3: Memory + Policy Index**, **M4: Grounded Policy RAG**, **M5: LangGraph Workflow**, **M6: Multi-Agent Team + MCP Tools**, **M7: Tracing + Reliability**, and **M8: Golden Eval + FastAPI Packaging**. M1 converts raw customer support messages into validated structured tickets. M2 takes those tickets and proposes the next operational action through deterministic policy tools. M3 persists per-customer interaction memory and builds a Qdrant index over ShopSense policy documents. M4 answers policy questions using hybrid retrieval, reranking, citations, and groundedness checks. M5 connects those modules into a checkpointed workflow with human-approval interrupts. M6 exposes the mock order/refund/shipping APIs through MCP and wraps the system as named agents. M7 adds trace capture plus retries, circuit breaking, and human-queue fallback for flaky tool calls. M8 adds a 20-ticket golden evaluation, final guardrails, and a FastAPI demo endpoint.

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
- M6 MCP tool server under `src/capstone/mcp/server.py`
- M6 multi-agent team under `src/capstone/team/multi_agent.py`
- M7 tracing under `src/capstone/observability/tracing.py`
- M7 reliability wrappers under `src/capstone/reliability/tools.py`
- M8 FastAPI app under `src/capstone/api.py`
- M8 guardrails under `src/capstone/guardrails.py`
- M8 golden eval set under `data/shopsense/eval/golden_m8_tickets.json`
- M1 evaluation script under `scripts/run_intake_eval.py`
- Unit tests under `tests/unit/`
- Latest committed M1 report under `evaluation/reports/m1_holdout_n60_v4.json`
- Latest committed M8 report under `evaluation/reports/m8_golden_eval.json`

Secrets, virtual environments, caches, and runtime state are intentionally excluded from Git.

## Evaluator Quick Start (live external services)

Everything below runs against the real services you configure: the LLM provider, **Qdrant Cloud** for the policy index, and **Langfuse** for traces. Needs Python 3.10 or newer. Total time is about 15 minutes.

**1. Install**

```bash
git clone https://github.com/abhraj786/iith-ai-capstone-shopsense.git
cd iith-ai-capstone-shopsense
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

**2. Add your keys.** Copy the template and fill in the values. `.env` is git-ignored and is never printed or logged.

```bash
cp .env.example .env
```

| Service | Variables in `.env` | Notes |
| --- | --- | --- |
| LLM (any LiteLLM provider) | `CAPSTONE_LLM_MODEL` and the matching key, e.g. `GEMINI_API_KEY` (default model `gemini/gemini-flash-lite-latest`) or `GROQ_API_KEY` with `groq/openai/gpt-oss-20b` | The Gemini key also gives real embeddings (Gemini) for retrieval; without it a hash fallback is used |
| Qdrant Cloud | `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION` (default `shopsense_policy_m3`) | The policy collection is created on the first run if it does not exist |
| Langfuse | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` (for example `https://cloud.langfuse.com`) | `CAPSTONE_LANGFUSE_*` aliases also work |

**3. Check the keys work** (prints OK or FAIL per service, never a key):

```bash
python -m scripts.check_setup
```

**4. Run every milestone, M1 to M8, against the live services:**

```bash
python demo_milestones.py --real
```

This is strict: it stops with the name of any missing key or unreachable service, and never falls back to fixtures. It runs intake (M1), action planning (M2), memory and policy index (M3), policy RAG (M4), the LangGraph workflow with a human pause (M5), the multi-agent team over MCP (M6), traces and reliability (M7), and the `/chat` API path with guardrails (M8). Traces appear in your Langfuse project.

**5. Run the evaluations** (the policy index is the Qdrant Cloud collection whenever the Qdrant keys are set):

```bash
python -m pytest tests -q                                  # 98 passed (offline by design, never touches the cloud)
python scripts/run_m8_golden_eval.py --live                # 20 of 20: live LLM parsing, then agents and guardrails
python -m scripts.run_m8_component_eval --judge --langfuse # 20 component items, LLM judge, Langfuse experiment
python scripts/run_policy_eval.py --use-configured-index   # M4 groundedness on the cloud collection: 5 of 5
```

**6. Call the API** (it uses the same live LLM, Qdrant Cloud and Langfuse):

```bash
uvicorn capstone.api:app --port 8000          # terminal 1
python demo_api_client.py --live              # terminal 2: English messages in, full JSON out
```

Or import `docs/postman/shopsense_chat.postman_collection.json` into Postman (tickets A, B, C, and an empty text that returns 422). To reach it from another machine, expose the port with a tunnel such as ngrok and set the collection's `base_url` to that address.

Why each command exists is in [docs/architecture.md](docs/architecture.md). With no keys at all, every command above still runs on a local in-memory index (the unit tests always do), so the project can be smoke-tested without accounts: `python demo_milestones.py --offline`.

If your LLM provider returns a temporary capacity error, retry or point `CAPSTONE_LLM_MODEL` at another model your account can use.

## Environment Reference

Full list of variables. Never commit `.env`.

```bash
CAPSTONE_LLM_MODEL=gemini/gemini-flash-lite-latest   # or groq/openai/gpt-oss-20b, openai/..., anthropic/...
GEMINI_API_KEY=<key>        # also used for embeddings
GROQ_API_KEY=<key>          # only if you use a groq/ model
OPENAI_API_KEY=<key>        # only if you use an openai/ model

QDRANT_URL=<your-cluster-url>
QDRANT_API_KEY=<your-qdrant-key>
QDRANT_COLLECTION=shopsense_policy_m3

LANGFUSE_PUBLIC_KEY=<key>
LANGFUSE_SECRET_KEY=<key>
LANGFUSE_HOST=https://cloud.langfuse.com
```

Runtime traces are always also written locally under `runtime/traces` as an audit copy. Setting `CAPSTONE_QDRANT=memory` forces a throwaway in-memory index even when Qdrant keys are present (the unit tests do this).

## Milestone Verification Matrix

Use the real-mode commands for final review. Use unit tests and offline demos for regression checks.

| Milestone | What to verify | Command |
| --- | --- | --- |
| M1 | LLM intake parser creates validated `SupportTicket` objects | `python scripts/run_intake_eval.py --n 60 --offset 60 --out evaluation/reports/m1_holdout_n60_v4.json` |
| M2 | Tool-backed action planning, refund caps, customer-scoped lookups | `python -m pytest tests/unit/test_action_agent.py tests/unit/test_tools.py -q` |
| M3 | Customer memory and Qdrant policy index | `python -m pytest tests/unit/test_memory.py tests/unit/test_policy_index.py -q` |
| M4 | Hybrid policy RAG and groundedness eval | `python scripts/run_policy_eval.py` |
| M5 | LangGraph workflow with auto path and human interrupt path | `python -m pytest tests/unit/test_workflow.py -q` |
| M6 | Multi-agent team and MCP-backed tool calls | `python -m pytest tests/unit/test_mcp_tools.py tests/unit/test_multi_agent_team.py -q` |
| M7 | Langfuse tracing, retry, fallback, circuit breaker | `python -m pytest tests/unit/test_reliability.py -q` |
| M8 | Golden eval, guardrails, FastAPI package | `python scripts/run_m8_golden_eval.py` |

For a single all-up check:

```bash
python -m pytest tests/unit -q
python scripts/run_policy_eval.py
python scripts/run_m8_golden_eval.py
python demo_milestones.py --real
```

If the LLM provider returns a temporary capacity error, retry or set another LiteLLM-compatible model that is available to your account:

```bash
CAPSTONE_LLM_MODEL=<provider>/<model-name>
```

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
98 passed
```

## Run Local Workbench UI

Use the workbench to test the milestone flow from a browser:

```bash
python -m capstone.workbench.app --port 8765
```

Then open:

```text
http://127.0.0.1:8765
```

The UI supports full M1+M2 runs, M2-only runs from pasted `SupportTicket` JSON,
M5 workflow runs from JSON, and M6 multi-agent runs through MCP. In M5 mode,
use the safe sample to see the `auto_execute` path and the legal sample to see
the `human_interrupt` path, then approve or reject the paused workflow from the
same screen. In M6 mode, the output includes named agent steps, MCP transport,
and M7 trace metadata. Full M1+M2 runs require the same `.env` model
configuration used by the M1 evaluation script.

Build or refresh the M3/M4 policy index directly:

```bash
python scripts/build_policy_index.py
```

By default this helper uses local persistent Qdrant under `runtime/qdrant`, so smoke tests can run without private credentials. To use Qdrant Cloud, add the same variables used in the course Colab to `.env`:

```bash
QDRANT_URL=...
QDRANT_API_KEY=...
QDRANT_COLLECTION=shopsense_policy_m3
```

For strict examiner testing of cloud behavior, run `python demo_milestones.py --real`; that command requires Qdrant Cloud and does not fall back. The standalone index helper may use local Qdrant for no-key development.

Run M4 groundedness evaluation:

```bash
python scripts/run_policy_eval.py
```

To run the evaluation against the configured persistent index instead of the isolated
in-memory test index:

```bash
python scripts/run_policy_eval.py --use-configured-index
```

## Run M6 MCP Server

M6 exposes the same deterministic mock APIs through an MCP server:

```bash
python -m capstone.mcp.server
```

The server registers customer/order lookup, shipment tracking, eligibility,
refund calculation, refund creation, replacement creation, approval-tier lookup,
and human-queue tools. These call the same M2 Python tool layer, so chat and
email channels share the same safety rules.

The team can also use the lab-style MCP path through `ShopSenseMCPClient`:

```text
MultiAgentTeam -> MCP client -> MCP server -> deterministic Python tools
```

MCP is the default: every order tool call (eligibility, refund amount, approver
tier, tracking, final write) goes through the MCP server, including from the
`/chat` API. If the MCP server cannot be reached at all, `FailoverToolGateway`
runs that call on the in-process gateway and says so (`failover` in the result,
"via python" in the step summary). A tool that answers `ok: false` is never
re-run elsewhere. Set `CAPSTONE_TOOL_TRANSPORT=python` to stay in-process (the
unit tests do this).
The M6 tests include a protocol-backed call that discovers and invokes the
running MCP server over stdio.

Run the M6 tests:

```bash
python -m pytest tests/unit/test_mcp_tools.py tests/unit/test_multi_agent_team.py -q
```

Expected:

```text
20 passed
```

## Run M7 Reliability And Tracing Tests

M7 traces ticket-resolution flows locally and forwards to LangFuse when
`CAPSTONE_LANGFUSE_PUBLIC_KEY` and `CAPSTONE_LANGFUSE_SECRET_KEY` are present.
Without keys, traces are still written under `runtime/traces/` so evaluation is
fully offline-capable.

For the strict external-cloud walkthrough, Langfuse is required:

```bash
python demo_milestones.py --real
```

That command initializes the Langfuse client in strict mode and fails early if
the keys or host are invalid. The regular API and tests keep writing local
JSONL traces as a durable audit copy.

```bash
python -m pytest tests/unit/test_reliability.py -q
```

Expected:

```text
8 passed
```

The tests cover retrying transient failures, opening a circuit after repeated
failures, falling back to the human queue when an order/shipping tool is down,
and writing an inspectable trace JSONL file.

Run the lab-style seeded reliability benchmark:

```bash
python scripts/run_reliability_benchmark.py --n 200
```

Expected:

```text
stage,ok,transient_or_fallback,malformed,success_or_handled_rate
baseline,114,70,16,0.570
hardened,179,21,0,1.000
```

Summarize any emitted trace as a small latency/fallback dashboard:

```bash
python scripts/summarize_trace.py runtime/traces/<trace_id>.jsonl
```

## Run M8 API And Golden Eval

Start the packaged FastAPI demo endpoint:

```bash
uvicorn capstone.api:app --reload --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Run end-user style demo cases from a second terminal:

```bash
python demo_api_client.py
```

By default the demo uses parsed tickets from the M8 golden set, so it is
deterministic and works without an LLM key. To test the full live M1 parser,
configure the model key in `.env` and run:

```bash
python demo_api_client.py --live
```

For a public tunnel, point the same client at the exposed base URL:

```bash
python demo_api_client.py --url https://<your-ngrok-id>.ngrok-free.app
```

Run the component-level eval (tool use, retrieval, planning, final answer). Add `--judge` for the LLM judge
and the deterministic-vs-judge disagreement list, and `--langfuse` for a Langfuse experiment:

```bash
python -m scripts.run_m8_component_eval --judge --langfuse
```

Container and Postman: `docker compose up --build` (needs a `.env`), then import
`docs/postman/shopsense_chat.postman_collection.json` and set `base_url` (localhost or the ngrok URL).

Run the 20-ticket M8 golden eval:

```bash
python scripts/run_m8_golden_eval.py
```

Expected:

```text
{
  "total": 20,
  "passed": 20,
  "failed": 0,
  "accuracy": 1.0
}
```

The eval covers angry, ambiguous, legal, high-refund, product-safety, repeat-contact,
and prompt-injection tickets. It verifies refund-cap guardrails, policy-grounding
guardrails, and safe human routing without requiring live LLM keys.

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
- Qdrant Cloud is used when `QDRANT_URL` and `QDRANT_API_KEY` are configured. The strict `demo_milestones.py --real` path requires cloud connectivity; the local helper scripts can use persistent Qdrant under `runtime/qdrant` for no-key regression runs.
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

## M6 Design

M6 separates the system into named agents and exposes the operational tools over MCP.

- `ShopSenseToolGateway` is the shared facade around order lookup, tracking, refund, replacement, calculator, approval, and human-queue tools.
- `capstone.mcp.server` exposes those functions through `FastMCP`.
- `ShopSenseMCPClient` can discover and call the MCP server over stdio, matching the lab-style protocol flow.
- `MultiAgentTeam` runs Triage Agent, Supervisor Agent, Memory Agent, Policy RAG Agent, Order-Actions Agent, and Escalation Reviewer Agent.
- The Supervisor (`team/supervisor.py`) is an LLM router. It sees only the structured ticket and picks `full`, `fast_track` (plain tracking or product questions) or `escalate_now` (legal or safety tickets). Code computes which routes are allowed for the ticket, so a risky ticket can only get `full`; an off-menu answer or an LLM failure falls back to `full`. The reviewer and the write step run after every route.
- Revision loop: if the reviewer finds the policy answer ungrounded for a refund or replacement, it sends the plan back for a wider policy lookup, at most `MAX_REVISIONS` (2) times, then a human decides.
- The team accepts a `channel` field, so chat and email tickets use the same tool boundary.
- Tests verify customer-scoped MCP order access, refund calculator exposure, protocol-backed tool invocation, legal-ticket escalation, and shared tools across chat/email.

## M7 Design

M7 adds observability and reliability around the M6 agent/tool boundary.

- `TraceRecorder` writes one JSONL trace per ticket flow under `runtime/traces/`.
- If Langfuse keys are configured, the same trace/span events are forwarded to Langfuse.
- In strict real mode, Langfuse initialization is required so the examiner can verify cloud observability instead of only local JSONL traces.
- Each trace has session/user metadata and tags for filtering.
- Each multi-agent step is traced: triage, memory, policy RAG, order action, and escalation review.
- Policy retrieval and concrete tool calls are nested child spans.
- `scripts/summarize_trace.py` builds the local per-span latency/error/fallback table.
- `ReliableToolGateway` retries transient tool failures with exponential backoff.
- `CircuitBreaker` opens after repeated failures, then goes half-open after the cooldown: exactly one trial call is let through, success closes it, failure re-opens it at once.
- Transient and malformed tool failures fall back to the human queue so customer cases are not dropped.
- `scripts/run_reliability_benchmark.py` provides a seeded before/after hardening benchmark (seed 42, 200 calls: 57% clean at baseline; with retries and the human-queue fallback 179 clean + 21 handed to a person = 100% handled) and a breaker demo (dead dependency: 3 real calls, 7 short-circuited).
- Triage and Supervisor are traced as Langfuse *generation* spans with model, input/output tokens and cost; `summarize_trace.py` shows tokens and cost per agent.
- `scripts/run_tracing_overhead.py` measures what tracing costs (about +0.5 ms local, +1.5 ms with Langfuse per ticket). Langfuse events are batched in the background; set `CAPSTONE_LANGFUSE_FLUSH_EACH_TRACE=true` to flush per ticket (this made each ticket about 200 ms slower).
- If the language model is down, `/chat` returns a safe answer instead of an error: the case is queued for a human (`trace.degraded = llm_unavailable`).

## M8 Design

M8 packages the assistant for evaluator use.

- `capstone.api` exposes `/health` and `/chat` through FastAPI.
- `/chat` can run raw-text flows or deterministic parsed-ticket flows for offline evaluation.
- `apply_guardrails` blocks prompt-injection instructions, prevents auto-approved over-cap refunds, and blocks ungrounded policy answers.
- `data/shopsense/eval/golden_m8_tickets.json` contains 20 golden cases spanning angry, ambiguous, legal, high-refund, product-safety, and prompt-injection scenarios.
- `scripts/run_m8_golden_eval.py` validates the golden set and writes `evaluation/reports/m8_golden_eval.json`.
- Unit tests cover guardrails, API packaging, and the M8 golden eval path.
