"""M6 supervisor: an LLM picks the route, code decides which routes are allowed.

The model sees only the structured ticket, never the raw customer text. Whatever it answers is
clamped to a menu that code computes from the ticket's risk fields, so a fooled or failing model
can at worst pick the full path. The reviewer and the write step run after every route.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from capstone.llm.client import LLMClient, LLMError
from capstone.schemas.intake import EscalationSignal, IssueType, Sentiment, SupportTicket, Urgency
from capstone.settings import PROJECT_ROOT


class Route(str, Enum):
    full = "full"
    fast_track = "fast_track"
    escalate_now = "escalate_now"


class SupervisorDecision(BaseModel):
    route: Route
    reason: str = Field(..., max_length=300)


FAST_TRACK_ISSUES = {IssueType.track_order, IssueType.product_information}


def allowed_routes(ticket: SupportTicket) -> set[Route]:
    """Routes the model may pick for this ticket. Computed from fields, not from model output."""
    allowed = {Route.full}
    risky = bool(
        ticket.prompt_injection_suspected or ticket.escalation_signals or ticket.missing_fields
        or ticket.claimed_amount_inr is not None
        or ticket.sentiment in {Sentiment.angry, Sentiment.distressed}
        or ticket.urgency in {Urgency.high, Urgency.critical}
    )
    if ticket.issue_type in FAST_TRACK_ISSUES and not risky:
        allowed.add(Route.fast_track)
    if {EscalationSignal.legal_or_regulatory, EscalationSignal.product_safety} & set(ticket.escalation_signals):
        allowed.add(Route.escalate_now)
    return allowed


def _view(ticket: SupportTicket) -> str:
    return (
        f"issue_type: {ticket.issue_type.value}\nsentiment: {ticket.sentiment.value}\n"
        f"urgency: {ticket.urgency.value}\nclaimed_amount_inr: {ticket.claimed_amount_inr}\n"
        f"escalation_signals: {[s.value for s in ticket.escalation_signals]}\n"
        f"prompt_injection_suspected: {ticket.prompt_injection_suspected}\n"
        f"missing_fields: {ticket.missing_fields}\nsummary: {ticket.summary[:200]}"
    )


def decide_route(client: LLMClient, ticket: SupportTicket) -> dict[str, Any]:
    allowed = allowed_routes(ticket)
    try:
        decision = client.structured(
            (Path(PROJECT_ROOT) / "prompts" / "supervisor.md").read_text(), _view(ticket), SupervisorDecision)
    except LLMError as e:
        return {"route": Route.full.value, "source": "fallback_full_path", "llm_route": None,
                "reason": f"Supervisor unavailable, using the full path ({str(e)[:80]})."}
    if decision.route in allowed:
        return {"route": decision.route.value, "source": "llm", "llm_route": decision.route.value,
                "reason": decision.reason}
    return {"route": Route.full.value, "source": "code_override", "llm_route": decision.route.value,
            "reason": f"Model chose {decision.route.value}, not allowed for this ticket; using the full path."}
