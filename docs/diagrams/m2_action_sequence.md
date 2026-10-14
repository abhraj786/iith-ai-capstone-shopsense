# M2 Action planning: sequence diagram (same sample as M1)

Source: `src/capstone/agents/action_agent.py` (`plan_action`) and `src/capstone/tools/` (lookups, calculators, actions).

Design rule: no LLM in M2. Fixed rules and the policy data tables decide, so wording cannot talk the system into an action.

**Input is the M1 output for the hostile sample** (customer `KW-C-00317`, today `2026-07-16`, `execute=False`):

| Field | Value |
|---|---|
| issue_type | damaged_delivery |
| order_ref | KW-O-000000 |
| sentiment | angry |
| claimed_amount_inr | 12999 |
| escalation_signals | angry_or_abusive, refund_above_auto_cap |
| prompt_injection_suspected | true (handled by the M8 guardrail layer, not by M2) |

```mermaid
sequenceDiagram
    autonumber
    participant M as M1 ticket
    participant P as plan_action
    participant T as Tools + data tables
    participant H as Human queue

    M->>P: SupportTicket (angry, KW-O-000000, claim 12999,<br/>signals angry_or_abusive + refund_above_auto_cap)<br/>customer KW-C-00317, today 2026-07-16, execute=False
    P->>P: Order ID present? Yes, so no request for more info
    rect rgb(255, 240, 240)
    P->>P: Red flag? Priority list: legal no, safety no,<br/>refund_above_auto_cap YES. STOP at the first match
    end
    Note over P,T: Tools are NOT called on this path
    P->>H: flag_for_human(trigger=refund_above_auto_cap,<br/>note="Angry, damaged order, demands 12999")<br/>proposed only: nothing is written
    P-->>M: ActionProposal: human_review, requires_human=true,<br/>executed=false

    Note over P,T: Had the tools run: order belongs to this customer, delivered 3 days ago,<br/>eligible (30-day window), refund 12999 from the ORDER PRICE,<br/>required approver = ops_manager (a human). Same answer.
```

## Priority list used in step 3

legal_or_regulatory, product_safety, refund_above_auto_cap, delivery_dispute, angry_or_abusive, repeat_contact, human_requested. The first one present wins.

## The path a safe ticket takes instead (calm, Rs 299, own order)

1. Order ID present: yes.
2. Red flag: none.
3. `check_eligibility`: delivered 3 days ago, Furniture defect window is 7, so eligible.
4. `calculate_refund`: Rs 299, computed from the order value.
5. `required_approver`: `auto`, so no human needed.
6. Output: `refund` via `issue_refund`. It is only performed when `execute=True`.
