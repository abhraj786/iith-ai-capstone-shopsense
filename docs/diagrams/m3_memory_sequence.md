# M3 Memory: sequence diagram (the same customer, over eight tickets)

Source: `src/capstone/memory/store.py` (`CustomerMemoryStore`), `src/capstone/memory/summarizer.py`, `src/capstone/agents/intake_agent.py` (`apply_contact_count`).

Design rule: the notebook never decides anything. It records every ticket, keeps the newest 5 verbatim, condenses older ones with the LLM, and supplies one number (earlier contacts) that code turns into the `repeat_contact` flag. M2's rules act on that flag.

**The story.** Customer `KW-C-00317` is the angry customer from M1 and M2. Real output of the code:

| Date | Channel | What she wrote | Earlier contacts found | contact_number | Flag added |
|---|---|---|---|---|---|
| 2026-07-16 | twitter | The hostile ticket: damaged `KW-O-000000`, demands 12999 | 0 | 1 | none |
| 2026-07-17 | email | "Still no replacement. Leave parcels at the back gate, the doorbell is broken, and I am allergic to peanuts." | 1 | 2 | none |
| 2026-07-18 | chat | "Any update on my damaged order?" (she never says it is her third message) | 2 | 3 | **repeat_contact** |
| 2026-07-19 to 23 | chat | Five tracking questions about other orders | 0 each | 1 | none |

After the eighth ticket the three oldest are condensed by the LLM:

> Customer awaiting replacement and 12999 refund for damaged delivery on order KW-O-000000; checked status on 2026-07-18 with no resolution yet. Preferences: leave parcels at the back gate due to a broken doorbell. Safety: allergic to peanuts.

```mermaid
sequenceDiagram
    autonumber
    participant T as Ticket (M1 output)
    participant S as Memory store
    participant F as Customer file (JSON)
    participant L as LLM summarizer

    T->>S: 18 Jul, chat, KW-O-000000, damaged_delivery, contact_number = 1
    S->>F: prior_contacts(KW-C-00317, KW-O-000000, damaged_delivery, 18 Jul, chat)
    F-->>S: 2 earlier (16 Jul twitter, 17 Jul email); this message's own date and channel excluded
    Note over S: contact_number = max(1, 2 + 1) = 3, so code adds repeat_contact
    S-->>T: ticket with contact_number 3 and repeat_contact (M2 now routes to a human)
    T->>S: after M2 decides: append_ticket(ticket, action)
    S->>F: add the event (date, channel, issue, order, mood, signals, action)
    Note over S,F: Newest 5 tickets stay verbatim. Others have summarized_upto = 0 so far
    S->>L: tickets 1 to 3 + previous summary (only on the 8th ticket)
    L-->>S: updated summary keeps order, back gate, doorbell, peanut allergy
    S->>F: save history_summary, summarized_upto = 3 (raw tickets never deleted)
    S-->>T: context: ticket_count 8, 5 recent tickets, rolling summary
```

If the LLM fails, the ticket is still handled, the raw tickets stay on disk, and the same tickets are retried on the next write.
A message re-sent on the same day and channel is not counted as a new contact, so re-running a demo cannot escalate itself.

Checks: `pytest tests/unit/test_memory.py tests/unit/test_intake.py` and `python scripts/run_memory_recall_check.py` (real LLM, plants a fact and fails if the summary loses it).
