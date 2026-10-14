"""M3 recall check: plant a fact early, add many tickets, then test the summary still holds it.

Summarizing is lossy, so this runs the real LLM summarizer and fails if the planted facts are lost.
Run: python scripts/run_memory_recall_check.py
"""

import sys
import tempfile
from pathlib import Path

from capstone.memory.store import CustomerMemoryStore
from capstone.memory.summarizer import make_llm_summarizer
from capstone.schemas.intake import IssueType, Sentiment, SupportTicket, Urgency

PLANTED = "Please deliver to the back gate, the doorbell is broken and I am allergic to peanuts."
MUST_SURVIVE = ["back gate", "peanut"]


def ticket(i: int, summary: str) -> SupportTicket:
    return SupportTicket(
        issue_type=IssueType.delivery_delay, order_ref=f"KW-O-00000{i}", sentiment=Sentiment.calm,
        urgency=Urgency.normal, claimed_amount_inr=None, contact_number=1, escalation_signals=[],
        prompt_injection_suspected=False, missing_fields=[], summary=summary)


def main() -> int:
    store = CustomerMemoryStore(Path(tempfile.mkdtemp()), summarizer=make_llm_summarizer())
    store.append_ticket("KW-C-00317", ticket(1, PLANTED), channel="twitter", received_at="2026-07-01")
    for i in range(2, 9):
        store.append_ticket("KW-C-00317", ticket(i, f"Parcel {i} arrived a day late."),
                            channel="email", received_at=f"2026-07-{i:02d}")
    ctx = store.customer_context("KW-C-00317")
    print("tickets stored        :", ctx["ticket_count"])
    print("verbatim (recent)     :", len(ctx["recent_tickets"]))
    print("history summary       :", ctx["history_summary"])
    missing = [f for f in MUST_SURVIVE if f not in ctx["rolling_summary"].lower()]
    print("planted facts survived:", "YES" if not missing else f"NO, lost {missing}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
