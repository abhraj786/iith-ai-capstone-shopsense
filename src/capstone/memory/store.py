"""Persistent per-customer memory (M3).

Memory is deliberately small and inspectable: one JSON file per customer. It stores
preferences and compact ticket/action history, while immutable order truth remains in the
mock API tables.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from capstone.schemas.actions import ActionProposal
from capstone.schemas.intake import SupportTicket
from capstone.settings import PROJECT_ROOT, get_settings


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
                "tickets": [],
                "last_updated_at": None,
            }
        return json.loads(path.read_text())

    def save(self, memory: dict[str, Any]) -> dict[str, Any]:
        memory["last_updated_at"] = datetime.now(timezone.utc).isoformat()
        path = self._path(memory["customer_ref"])
        path.write_text(json.dumps(memory, indent=2, sort_keys=True))
        return memory

    def remember_preference(self, customer_ref: str, key: str, value: str) -> dict[str, Any]:
        memory = self.load(customer_ref)
        memory.setdefault("preferences", {})[key] = value
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
        return self.save(memory)

    def customer_context(self, customer_ref: str, limit: int = 5) -> dict[str, Any]:
        memory = self.load(customer_ref)
        tickets = memory.get("tickets", [])
        return {
            "customer_ref": customer_ref,
            "preferences": memory.get("preferences", {}),
            "recent_tickets": tickets[-limit:],
            "ticket_count": len(tickets),
            "last_updated_at": memory.get("last_updated_at"),
        }


def get_memory_store() -> CustomerMemoryStore:
    settings = get_settings()
    return CustomerMemoryStore(PROJECT_ROOT / settings.runtime_root / "memory" / "customers")
