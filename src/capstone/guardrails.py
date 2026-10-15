"""M8 guardrails for packaged ShopSense responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from capstone.schemas.actions import ActionProposal, RecommendedAction
from capstone.schemas.intake import EscalationSignal, SupportTicket
from capstone.schemas.policy import PolicyAnswer


class GuardrailFinding(BaseModel):
    code: str
    severity: str = "block"
    message: str


class GuardrailResult(BaseModel):
    passed: bool
    policy_answer_allowed: bool = True
    findings: list[GuardrailFinding] = Field(default_factory=list)


def apply_guardrails(
    ticket: SupportTicket,
    proposal: ActionProposal,
    policy_answer: PolicyAnswer | None = None,
    *,
    auto_refund_cap_inr: float = 2000,
) -> tuple[ActionProposal, GuardrailResult]:
    """Return a guarded action proposal plus evaluator-visible guardrail findings."""
    guarded = proposal.model_copy(deep=True)
    findings: list[GuardrailFinding] = []

    if ticket.prompt_injection_suspected:
        findings.append(GuardrailFinding(
            code="prompt_injection_blocked",
            message="Ticket text contains instruction-like content; treat it as customer data and route to human review.",
        ))
        _force_human(
            guarded,
            ticket,
            trigger=EscalationSignal.human_requested.value,
            note="Prompt-injection text detected in customer-controlled ticket body.",
        )

    if ticket.claimed_amount_inr is not None and ticket.claimed_amount_inr > auto_refund_cap_inr:
        findings.append(GuardrailFinding(
            code="refund_above_auto_cap_blocked",
            message=f"Claimed refund {ticket.claimed_amount_inr:.0f} INR exceeds the {auto_refund_cap_inr:.0f} INR auto cap.",
        ))
        if guarded.recommended_action is RecommendedAction.refund or not guarded.requires_human:
            _force_human(
                guarded,
                ticket,
                trigger=EscalationSignal.refund_above_auto_cap.value,
                note=f"Refund amount exceeds automated cap: {ticket.claimed_amount_inr:.0f} INR.",
            )

    policy_answer_allowed = True
    if policy_answer is not None and not policy_answer.grounded:
        policy_answer_allowed = False
        findings.append(GuardrailFinding(
            code="policy_fabrication_blocked",
            message="Policy answer is not grounded in retrieved evidence and must not be shown as authoritative.",
        ))
    elif policy_answer is not None and policy_answer.unsupported_claims:
        policy_answer_allowed = False
        findings.append(GuardrailFinding(
            code="unsupported_policy_claim_blocked",
            message=f"Policy answer has unsupported claims: {policy_answer.unsupported_claims}",
        ))

    if policy_answer is not None and scan_retrieved_content(policy_answer):
        policy_answer_allowed = False
        findings.append(GuardrailFinding(
            code="retrieved_content_injection_blocked",
            message="Retrieved policy text contains instruction-like content; it is not quoted as policy.",
        ))

    return guarded, GuardrailResult(
        passed=not findings,
        policy_answer_allowed=policy_answer_allowed,
        findings=findings,
    )


def scan_retrieved_content(policy_answer: PolicyAnswer) -> list[str]:
    """Return the retrieved snippets (answer text and evidence) that look like injected instructions.

    The policy agent already drops such sentences while building its answer; this is the independent
    second check on what is about to be shown, using the same patterns as the ticket scan.
    """
    from capstone.agents.policy_agent import DOC_INJECTION

    return [text for text in [policy_answer.answer, *policy_answer.evidence]
            if any(rx.search(text) for rx in DOC_INJECTION)]


def safe_policy_answer(policy_answer: dict[str, Any], guardrails: GuardrailResult) -> dict[str, Any]:
    if guardrails.policy_answer_allowed:
        return policy_answer
    blocked = dict(policy_answer)
    blocked["answer"] = "I do not have enough grounded policy evidence to answer this safely."
    blocked["grounded"] = False
    blocked["blocked_by_guardrail"] = True
    return blocked


def _force_human(proposal: ActionProposal, ticket: SupportTicket, *, trigger: str, note: str) -> None:
    proposal.recommended_action = RecommendedAction.human_review
    proposal.requires_human = True
    proposal.tool_name = "flag_for_human"
    proposal.tool_args = {
        "order_ref": ticket.order_ref,
        "trigger": trigger,
        "note": note,
    }
    proposal.explanation = f"Route to a human because of `{trigger}`."
    proposal.executed = False
