"""M2 action planning.

The intake model says what the customer appears to need. This module decides what the
system can safely do next using deterministic policy tools. Mutable side effects only
happen when the caller passes `execute=True`.
"""

from datetime import date

from capstone.schemas.actions import ActionProposal, RecommendedAction
from capstone.schemas.intake import EscalationSignal, IssueType, SupportTicket
from capstone.tools import actions, calculators, lookups
from capstone.tools.errors import ToolError
from capstone.tools.repository import Repository


REFUND_REASON_BY_ISSUE = {
    IssueType.refund_request: "quality",
    IssueType.return_request: "changed_mind",
    IssueType.damaged_delivery: "damaged",
    IssueType.missing_item: "not_delivered",
    IssueType.delivery_delay: "late_delivery",
    IssueType.cancel_order: "cancelled_before_dispatch",
}

REPLACEMENT_REASON_BY_ISSUE = {
    IssueType.damaged_delivery: "damaged",
    IssueType.wrong_item: "wrong_item",
}

ESCALATION_PRIORITY = [
    EscalationSignal.legal_or_regulatory,
    EscalationSignal.product_safety,
    EscalationSignal.refund_above_auto_cap,
    EscalationSignal.delivery_dispute,
    EscalationSignal.angry_or_abusive,
    EscalationSignal.repeat_contact,
    EscalationSignal.human_requested,
]

HUMAN_FIRST_SIGNALS = {
    EscalationSignal.human_requested,
    EscalationSignal.repeat_contact,
    EscalationSignal.angry_or_abusive,
    EscalationSignal.legal_or_regulatory,
    EscalationSignal.product_safety,
    EscalationSignal.delivery_dispute,
    EscalationSignal.refund_above_auto_cap,
}


def _missing_order(ticket: SupportTicket) -> ActionProposal | None:
    if ticket.order_ref:
        return None
    return ActionProposal(
        recommended_action=RecommendedAction.request_missing_info,
        explanation="Need the order reference before checking order policy or taking action.",
        tool_args={"missing_fields": sorted(set([*ticket.missing_fields, "order_ref"]))},
    )


def _human_trigger(ticket: SupportTicket) -> EscalationSignal | None:
    signals = set(ticket.escalation_signals)
    for signal in ESCALATION_PRIORITY:
        if signal in signals:
            return signal
    return None


def _queue_human(repo: Repository, customer_ref: str, order_ref: str | None,
                 trigger: str, note: str, execute: bool) -> ActionProposal:
    proposal = ActionProposal(
        recommended_action=RecommendedAction.human_review,
        requires_human=True,
        tool_name="flag_for_human",
        tool_args={"customer_ref": customer_ref, "order_ref": order_ref,
                   "trigger": trigger, "note": note},
        explanation=f"Route to a human because of `{trigger}`.",
    )
    if execute:
        try:
            proposal.executed = True
            proposal.tool_result = actions.flag_for_human(repo, customer_ref, order_ref, trigger, note)
        except ToolError as exc:
            proposal.tool_error = exc.to_dict()
    return proposal


def _unwrap(result: dict) -> dict:
    """Turn a tool-gateway reply ({ok, result|error}) back into a value or a ToolError."""
    if result.get("ok"):
        return result["result"]
    error = result.get("error") or {}
    raise ToolError(error.get("error", "tool_error"), error.get("message", "tool call failed"))


def _approval_or_eligibility_gate(repo: Repository, customer_ref: str, order_ref: str,
                                  reason_code: str, today: date, gateway=None) -> ActionProposal | None:
    """With a `gateway` (in-process or MCP) the policy calculators run through it; else directly."""
    if gateway is None:
        check = lambda: calculators.check_eligibility(repo, customer_ref, order_ref, reason_code, today)
        refund = lambda: calculators.calculate_refund(repo, customer_ref, order_ref, reason_code)
        approver = lambda amount: calculators.required_approver(repo, customer_ref, amount)
    else:
        check = lambda: _unwrap(gateway.check_eligibility(customer_ref, order_ref, reason_code, today.isoformat()))
        refund = lambda: _unwrap(gateway.calculate_refund(customer_ref, order_ref, reason_code))
        approver = lambda amount: _unwrap(gateway.required_approver(customer_ref, amount))
    try:
        eligibility = check()
        if eligibility.get("needs_dispute_investigation"):
            return ActionProposal(
                recommended_action=RecommendedAction.human_review,
                requires_human=True,
                reason_code=reason_code,
                tool_name="flag_for_human",
                tool_args={"customer_ref": customer_ref, "order_ref": order_ref,
                           "trigger": "delivery_dispute", "note": eligibility["why"]},
                explanation=f"Policy allows review, but this delivery dispute needs investigation: {eligibility['why']}",
            )
        if not eligibility["eligible"]:
            trigger = "delivery_dispute" if eligibility.get("needs_dispute_investigation") else "human_requested"
            return ActionProposal(
                recommended_action=RecommendedAction.human_review,
                requires_human=True,
                reason_code=reason_code,
                tool_name="flag_for_human",
                tool_args={"customer_ref": customer_ref, "order_ref": order_ref,
                           "trigger": trigger, "note": eligibility["why"]},
                explanation=f"Policy does not allow automatic action: {eligibility['why']}",
            )
        amount = refund()["refund_inr"]
        needed = approver(amount)
        if needed["is_human"] or needed["account_restricted"]:
            trigger = "account_under_review" if needed["account_restricted"] else "refund_above_auto_cap"
            return ActionProposal(
                recommended_action=RecommendedAction.human_review,
                requires_human=True,
                reason_code=reason_code,
                tool_name="flag_for_human",
                tool_args={"customer_ref": customer_ref, "order_ref": order_ref,
                           "trigger": trigger, "note": f"{amount:.0f} INR needs {needed['approver']} approval"},
                explanation=f"Refund is policy-valid but needs {needed['approver']} approval.",
            )
    except ToolError as exc:
        return ActionProposal(
            recommended_action=RecommendedAction.human_review,
            requires_human=True,
            reason_code=reason_code,
            explanation="Could not safely verify the order or policy; send to a human.",
            tool_error=exc.to_dict(),
        )
    return None


def plan_action(repo: Repository, ticket: SupportTicket, customer_ref: str,
                today: date, execute: bool = False, gateway=None) -> ActionProposal:
    """Return the safest next action for a parsed ticket.

    Read-only lookups may be performed while planning. Refund/replacement/queue writes
    happen only when `execute=True`.
    """
    if missing := _missing_order(ticket):
        return missing

    if trigger := _human_trigger(ticket):
        return _queue_human(repo, customer_ref, ticket.order_ref, trigger.value, ticket.summary, execute)

    if ticket.issue_type is IssueType.track_order:
        proposal = ActionProposal(
            recommended_action=RecommendedAction.track_order,
            tool_name="track_shipment",
            tool_args={"customer_ref": customer_ref, "order_ref": ticket.order_ref},
            explanation="Use the shipment lookup for an order-status request.",
        )
        try:
            proposal.tool_result = lookups.track_shipment(repo, customer_ref, ticket.order_ref)
        except ToolError as exc:
            proposal.requires_human = True
            proposal.recommended_action = RecommendedAction.human_review
            proposal.tool_error = exc.to_dict()
            proposal.explanation = "Could not safely verify this order for the customer."
        return proposal

    if ticket.issue_type in REPLACEMENT_REASON_BY_ISSUE:
        reason = REPLACEMENT_REASON_BY_ISSUE[ticket.issue_type]
        if gate := _approval_or_eligibility_gate(repo, customer_ref, ticket.order_ref, reason, today, gateway):
            return gate
        proposal = ActionProposal(
            recommended_action=RecommendedAction.replacement,
            reason_code=reason,
            tool_name="create_replacement",
            tool_args={"customer_ref": customer_ref, "order_ref": ticket.order_ref,
                       "reason": reason, "today": today.isoformat(), "approved_by": "auto"},
            explanation="Eligible defect claim; propose an automatic replacement.",
        )
        if execute:
            try:
                proposal.executed = True
                proposal.tool_result = actions.create_replacement(repo, customer_ref, ticket.order_ref, reason, today)
            except ToolError as exc:
                proposal.tool_error = exc.to_dict()
        return proposal

    if ticket.issue_type in REFUND_REASON_BY_ISSUE:
        reason = REFUND_REASON_BY_ISSUE[ticket.issue_type]
        if gate := _approval_or_eligibility_gate(repo, customer_ref, ticket.order_ref, reason, today, gateway):
            return gate
        proposal = ActionProposal(
            recommended_action=RecommendedAction.refund,
            reason_code=reason,
            tool_name="issue_refund",
            tool_args={"customer_ref": customer_ref, "order_ref": ticket.order_ref,
                       "reason_code": reason, "today": today.isoformat(), "approved_by": "auto"},
            explanation="Eligible refund claim within automatic approval policy.",
        )
        if execute:
            try:
                proposal.executed = True
                proposal.tool_result = actions.issue_refund(repo, customer_ref, ticket.order_ref, reason, today)
            except ToolError as exc:
                proposal.tool_error = exc.to_dict()
        return proposal

    return _queue_human(
        repo, customer_ref, ticket.order_ref, "human_requested",
        f"No deterministic M2 action for {ticket.issue_type.value}: {ticket.summary}", execute,
    )
