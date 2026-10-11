# IITH AI Capstone: ShopSense

ShopSense customer-care and order-operations capstone for the IIT Hyderabad Applied AI program.

This repository currently implements **M1: Intake Parsing** and the first slice of **M2: Safe Action Planning**. M1 converts raw customer support messages into validated structured tickets. M2 takes those tickets and proposes the next operational action through deterministic policy tools.

## What Is Included

- ShopSense generated intake records under `data/shopsense/intake/`
- ShopSense mock policy/API tables under `data/shopsense/mock_api/`
- M1 intake prompt under `prompts/intake.md`
- Pydantic ticket schema under `src/capstone/schemas/intake.py`
- LiteLLM structured-output client under `src/capstone/llm/client.py`
- Intake parser under `src/capstone/agents/intake_agent.py`
- M2 action planner under `src/capstone/agents/action_agent.py`
- Deterministic lookup, policy, and action tools under `src/capstone/tools/`
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
33 passed
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
