"""LLM rolling summary for customer memory (M3).

Older tickets are condensed into a short summary that is merged with the previous one,
so concrete facts (delivery instructions, allergies, outcomes) are carried forward.
Summarizing is lossy, so scripts/run_memory_recall_check.py tests that a planted fact survives.
"""

from typing import Any

from pydantic import BaseModel

from capstone.llm.client import LLMClient

SYSTEM = (
    "You maintain a running summary of a customer's support history. Update the existing summary "
    "with the new ticket events, keeping concrete facts: order IDs, delivery instructions, "
    "allergies or safety details, preferences, amounts, and what was decided. Drop filler. "
    "Return only the updated summary, under 120 words."
)


class HistorySummary(BaseModel):
    summary: str


def _line(event: dict[str, Any]) -> str:
    action = event.get("recommended_action") or "none"
    return (f"[{event.get('received_at')} {event.get('channel')}] {event.get('issue_type')} on order "
            f"{event.get('order_ref')}, {event.get('sentiment')}: {event.get('summary')} (action: {action})")


def make_llm_summarizer(client: LLMClient | None = None):
    client = client or LLMClient()

    def summarize(events: list[dict[str, Any]], previous: str) -> str:
        user = (f"Existing summary:\n{previous or '(none)'}\n\nNew ticket events:\n"
                + "\n".join(_line(e) for e in events) + "\n\nUpdated summary:")
        return client.structured(SYSTEM, user, HistorySummary).summary.strip()

    return summarize
