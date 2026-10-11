"""Persistent per-customer memory (M3).

Memory is deliberately small and inspectable: one JSON file per customer. It stores
semantic preferences, episodic ticket/action history, and a compact rolling summary.
Immutable order truth remains in the mock API tables.
"""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from capstone.schemas.actions import ActionProposal
from capstone.schemas.intake import SupportTicket
from capstone.settings import PROJECT_ROOT, get_settings

SUMMARY_AFTER_TICKETS = 5
RECENT_TICKET_LIMIT = 5


class CustomerMemoryStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, customer_ref: str) -> Path:
        safe = customer_ref.replace("/", "_")
        return self.root / f"{safe}.json"

    def load(self, customer_ref: str) -> dict[str, Any]:
        path = self._path(customer_ref)
        if not path.exists():
            return {
                "customer_ref": customer_ref,
                "preferences": {},
                "rolling_summary": "No prior customer interactions recorded.",
                "memory_types": {
                    "semantic": "Customer preferences and stable traits.",
                    "episodic": "Timestamped support tickets and proposed actions.",
                    "procedural": "Resolution procedures are enforced by deterministic tools and policies.",
                },
                "tickets": [],
                "last_updated_at": None,
            }
        memory = json.loads(path.read_text())
        memory.setdefault("preferences", {})
        memory.setdefault("rolling_summary", self._summarize(memory.get("tickets", []), memory["preferences"]))
        memory.setdefault("memory_types", {
            "semantic": "Customer preferences and stable traits.",
            "episodic": "Timestamped support tickets and proposed actions.",
            "procedural": "Resolution procedures are enforced by deterministic tools and policies.",
        })
        memory.setdefault("tickets", [])
        return memory

    def save(self, memory: dict[str, Any]) -> dict[str, Any]:
        memory["last_updated_at"] = datetime.now(timezone.utc).isoformat()
        path = self._path(memory["customer_ref"])
        path.write_text(json.dumps(memory, indent=2, sort_keys=True))
        return memory

    def remember_preference(self, customer_ref: str, key: str, value: str) -> dict[str, Any]:
        memory = self.load(customer_ref)
        memory.setdefault("preferences", {})[key] = value
        memory["rolling_summary"] = self._summarize(memory.get("tickets", []), memory["preferences"])
        return self.save(memory)

    def append_ticket(self, customer_ref: str, ticket: SupportTicket,
                      action: ActionProposal | None = None,
                      channel: str | None = None,
                      received_at: str | None = None) -> dict[str, Any]:
        memory = self.load(customer_ref)
        event = {
            "received_at": received_at,
            "channel": channel,
            "issue_type": ticket.issue_type.value,
            "order_ref": ticket.order_ref,
            "sentiment": ticket.sentiment.value,
            "urgency": ticket.urgency.value,
            "escalation_signals": [s.value for s in ticket.escalation_signals],
            "summary": ticket.summary,
        }
        if action:
            event["recommended_action"] = action.recommended_action.value
            event["requires_human"] = action.requires_human
            event["tool_name"] = action.tool_name
        memory.setdefault("tickets", []).append(event)
        memory["rolling_summary"] = self._summarize(memory["tickets"], memory.get("preferences", {}))
        return self.save(memory)

    def customer_context(self, customer_ref: str, limit: int = 5) -> dict[str, Any]:
        memory = self.load(customer_ref)
        tickets = memory.get("tickets", [])
        return {
            "customer_ref": customer_ref,
            "preferences": memory.get("preferences", {}),
            "rolling_summary": memory.get("rolling_summary"),
            "memory_types": memory.get("memory_types", {}),
            "recent_tickets": tickets[-limit:],
            "ticket_count": len(tickets),
            "last_updated_at": memory.get("last_updated_at"),
        }

    def _summarize(self, tickets: list[dict[str, Any]], preferences: dict[str, str]) -> str:
        if not tickets:
            if preferences:
                prefs = ", ".join(f"{key}={value}" for key, value in sorted(preferences.items()))
                return f"No prior tickets recorded. Known preferences: {prefs}."
            return "No prior customer interactions recorded."

        issue_counts = Counter(ticket.get("issue_type", "unknown") for ticket in tickets)
        sentiment_counts = Counter(ticket.get("sentiment", "unknown") for ticket in tickets)
        action_counts = Counter(ticket.get("recommended_action", "none") for ticket in tickets)
        signals = Counter(
            signal
            for ticket in tickets
            for signal in ticket.get("escalation_signals", [])
        )
        repeat_note = ""
        if len(tickets) > SUMMARY_AFTER_TICKETS:
            repeat_note = f" Long-running customer history: {len(tickets)} recorded tickets."
        top_issues = ", ".join(f"{name} x{count}" for name, count in issue_counts.most_common(3))
        top_sentiment = sentiment_counts.most_common(1)[0][0]
        top_actions = ", ".join(f"{name} x{count}" for name, count in action_counts.most_common(2))
        signal_text = ", ".join(signal for signal, _ in signals.most_common(4)) or "none"
        latest = tickets[-1]
        prefs = ", ".join(f"{key}={value}" for key, value in sorted(preferences.items())) or "none"
        return (
            f"{len(tickets)} recorded support interaction(s). Common issues: {top_issues}. "
            f"Dominant sentiment: {top_sentiment}. Common actions: {top_actions}. "
            f"Escalation signals seen: {signal_text}. Preferences: {prefs}. "
            f"Latest ticket: {latest.get('issue_type')} for order {latest.get('order_ref')} "
            f"with {latest.get('sentiment')} sentiment.{repeat_note}"
        )


def get_memory_store() -> CustomerMemoryStore:
    settings = get_settings()
    return CustomerMemoryStore(PROJECT_ROOT / settings.runtime_root / "memory" / "customers")
