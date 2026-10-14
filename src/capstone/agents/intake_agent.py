"""Turn a raw customer message into a validated SupportTicket (M1).

Only the message text and channel reach the model. Ground-truth labels and customer/order
metadata never do. The model's output is then checked in code, because a model can invent an
order ID or miss a threshold; code can't be talked out of it.
"""

import re
from collections.abc import Callable
from pathlib import Path

from capstone.llm.client import LLMClient
from capstone.schemas.intake import EscalationSignal, IssueType, SupportTicket
from capstone.settings import PROJECT_ROOT

ORDER_REF = re.compile(r"\bKW-O-\d{6}\b", re.IGNORECASE)
NEEDS_ORDER = set(IssueType) - {IssueType.product_information, IssueType.other, IssueType.complaint}
MAX_TEXT_CHARS = 6000
# Deterministic injection screen. It runs in addition to the model's own flag: ticket text is
# attacker-controlled, so detection must not depend on the model noticing the attack.
INJECTION_PATTERNS = [re.compile(p, re.IGNORECASE) for p in (
    r"\b(ignore|disregard|forget|override|bypass)\b.{0,40}\b(instruction|rule|polic|cap|limit|guideline|prompt)",
    r"\b(system|assistant|developer)\s*(prompt|message|override|:)",
    r"</?\s*(ticket|system|instructions?)\s*>",
    r"\byou are now\b|\bnew (directive|instructions?)\b|\bpre-?approved\b|\bauthori[sz]ed by (the )?(admin|management|manager|ceo)\b",
    r"\b(admin|manager|management)\b.{0,40}\b(permission|approved|authori[sz]ed|allow(ed)?)\b",
    r"\b(cap|limit)\s+(hata|remove|lift|waive)|\b(hata|remove|lift|waive)\w*\s+(the\s+)?(cap|limit)\b",
    r"\bapprove\b.{0,30}\b(without|skip|no)\b.{0,20}\b(review|check|approval)",
    r"\b(reveal|print|show|repeat)\b.{0,30}\b(system prompt|instructions|api key|secret)",
)]


def looks_like_injection(text: str) -> bool:
    return any(p.search(text) for p in INJECTION_PATTERNS)
CODE_DECIDED_SIGNALS = {
    EscalationSignal.refund_above_auto_cap,
    EscalationSignal.repeat_contact,
}


def _system_prompt() -> str:
    return (Path(PROJECT_ROOT) / "prompts" / "intake.md").read_text()


def parse_ticket(client: LLMClient, raw_text: str, channel: str | None = None,
                 auto_refund_cap_inr: float | None = None,
                 repeat_contact_threshold: int | None = None,
                 prior_contacts: Callable[[SupportTicket], int] | None = None) -> SupportTicket:
    text = raw_text[:MAX_TEXT_CHARS]
    user = f"Channel: {channel or 'unknown'}\n<ticket>\n{text}\n</ticket>"
    ticket = client.structured(_system_prompt(), user, SupportTicket)

    # The order ID must literally appear in the customer's text, so the model can't invent one.
    found = {m.upper() for m in ORDER_REF.findall(text)}
    claimed = (ticket.order_ref or "").strip().upper()
    ticket.order_ref = claimed if claimed in found else (sorted(found)[0] if len(found) == 1 else None)
    if ticket.order_ref is None and ticket.issue_type in NEEDS_ORDER and "order_ref" not in ticket.missing_fields:
        ticket.missing_fields.append("order_ref")
    if ticket.order_ref and "order_ref" in ticket.missing_fields:
        ticket.missing_fields.remove("order_ref")

    # Ticket text is attacker-controlled, so a regex screen can only add to the model's injection flag.
    if looks_like_injection(text):
        ticket.prompt_injection_suspected = True

    # These signals depend on policy thresholds, so discard model guesses before recomputing.
    ticket.escalation_signals = [s for s in ticket.escalation_signals if s not in CODE_DECIDED_SIGNALS]

    # The cap comparison is arithmetic, so code decides it, not the model.
    if (auto_refund_cap_inr is not None and ticket.claimed_amount_inr is not None
            and ticket.claimed_amount_inr > auto_refund_cap_inr
            and EscalationSignal.refund_above_auto_cap not in ticket.escalation_signals):
        ticket.escalation_signals.append(EscalationSignal.refund_above_auto_cap)
    # Counting contacts against the policy threshold is also arithmetic, so code decides it.
    apply_contact_count(ticket, prior_contacts(ticket) if prior_contacts else 0, repeat_contact_threshold)
    return ticket


def apply_contact_count(ticket: SupportTicket, prior: int, threshold: int | None) -> SupportTicket:
    """Contact count = the larger of what the customer says and what memory recorded, plus this one."""
    ticket.contact_number = max(ticket.contact_number, prior + 1)
    if (threshold is not None and ticket.contact_number >= threshold
            and EscalationSignal.repeat_contact not in ticket.escalation_signals):
        ticket.escalation_signals.append(EscalationSignal.repeat_contact)
    return ticket
