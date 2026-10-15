"""Persistent per-customer memory (M3).

Memory is deliberately small and inspectable: one JSON file per customer. It stores
semantic preferences, episodic ticket/action history, and a compact rolling summary.
Immutable order truth remains in the mock API tables.
"""

import json
import logging
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from capstone.schemas.actions import ActionProposal
from capstone.schemas.intake import SupportTicket
from capstone.settings import PROJECT_ROOT, get_settings

MAX_KNOWN_FACTS = 20
SUMMARY_AFTER_TICKETS = 5
RECENT_TICKET_LIMIT = 5  # tickets kept verbatim (working memory); older ones are condensed

log = logging.getLogger(__name__)

# (old ticket events, previous history summary) -> updated history summary
Summarizer = Callable[[list[dict[str, Any]], str], str]


class CustomerMemoryStore:
    def __init__(self, root: Path, summarizer: Summarizer | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.summarizer = summarizer

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
                "history_summary": "",
                "summarized_upto": 0,
                "known_facts": [],
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
        memory.setdefault("history_summary", "")
        memory.setdefault("summarized_upto", 0)
        memory.setdefault("known_facts", [])
        return memory

    def save(self, memory: dict[str, Any]) -> dict[str, Any]:
        memory["last_updated_at"] = datetime.now(timezone.utc).isoformat()
        path = self._path(memory["customer_ref"])
        path.write_text(json.dumps(memory, indent=2, sort_keys=True))
        return memory

    def remember_preference(self, customer_ref: str, key: str, value: str) -> dict[str, Any]:
        memory = self.load(customer_ref)
        memory.setdefault("preferences", {})[key] = value
        memory["rolling_summary"] = self._rolling(memory)
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
        self._remember_facts(memory, ticket.customer_facts, received_at)
        self._condense_old_tickets(memory)
        memory["rolling_summary"] = self._rolling(memory)
        return self.save(memory)

    def prior_contacts(self, customer_ref: str, order_ref: str | None, issue_type: str,
                       received_at: str | None = None, channel: str | None = None) -> int:
        """How many earlier contacts this customer made about the same order and issue.

        Contacts are counted per (date, channel). Passing the current message's own date and
        channel excludes it, so re-sending the same message on the same day is not a new contact.
        """
        if not order_ref:
            return 0
        seen = {
            (t.get("received_at"), t.get("channel"))
            for t in self.load(customer_ref).get("tickets", [])
            if t.get("order_ref") == order_ref and t.get("issue_type") == issue_type
        }
        seen.discard((received_at, channel))
        return len(seen)

    def _remember_facts(self, memory: dict[str, Any], facts: list[str], learned_on: str | None) -> None:
        """Semantic memory: lasting facts the customer stated, kept apart from the ticket history."""
        known = memory.setdefault("known_facts", [])
        have = {k["fact"].lower() for k in known}
        for fact in facts:
            if fact.lower() not in have:
                known.append({"fact": fact, "learned_on": learned_on})
                have.add(fact.lower())
        del known[:-MAX_KNOWN_FACTS]

    def _condense_old_tickets(self, memory: dict[str, Any]) -> None:
        """Keep the newest tickets verbatim and fold older ones into the history summary.

        Only newly aged-out tickets are sent to the summarizer, together with the previous
        summary, so earlier facts are carried forward. If the summarizer fails the raw
        tickets stay on disk and the same tickets are retried on the next write.
        """
        if not self.summarizer:
            return
        tickets = memory["tickets"]
        start, cutoff = memory.get("summarized_upto", 0), len(tickets) - RECENT_TICKET_LIMIT
        if cutoff <= start:
            return
        try:
            memory["history_summary"] = self.summarizer(tickets[start:cutoff], memory.get("history_summary", ""))
            memory["summarized_upto"] = cutoff
        except Exception as exc:  # memory must never block handling a ticket
            log.warning("Memory summarization failed; will retry on the next ticket: %s", exc)

    def _rolling(self, memory: dict[str, Any]) -> str:
        counts = self._summarize(memory.get("tickets", []), memory.get("preferences", {}))
        history = memory.get("history_summary")
        text = f"{counts} Earlier history, condensed: {history}" if history else counts
        facts = "; ".join(k["fact"] for k in memory.get("known_facts", []))
        return f"{text} Known facts: {facts}." if facts else text

    def customer_context(self, customer_ref: str, limit: int = 5) -> dict[str, Any]:
        memory = self.load(customer_ref)
        tickets = memory.get("tickets", [])
        return {
            "customer_ref": customer_ref,
            "preferences": memory.get("preferences", {}),
            "rolling_summary": memory.get("rolling_summary"),
            "history_summary": memory.get("history_summary", ""),
            "known_facts": memory.get("known_facts", []),
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
    summarizer = None
    if settings.memory_llm_summary:
        from capstone.memory.summarizer import make_llm_summarizer  # lazy: needs the LLM stack
        summarizer = make_llm_summarizer()
    return CustomerMemoryStore(PROJECT_ROOT / settings.runtime_root / "memory" / "customers", summarizer)
