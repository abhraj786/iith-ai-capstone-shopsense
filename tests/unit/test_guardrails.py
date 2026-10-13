"""M8 guardrail tests."""

from capstone.guardrails import apply_guardrails
from capstone.schemas.actions import ActionProposal, RecommendedAction
from capstone.schemas.intake import IssueType, Sentiment, SupportTicket, Urgency
from capstone.schemas.policy import PolicyAnswer


def test_prompt_injection_routes_to_human_review():
    ticket = SupportTicket(
        issue_type=IssueType.refund_request,
        order_ref="KW-O-000950",
        sentiment=Sentiment.calm,
        urgency=Urgency.normal,
        claimed_amount_inr=500,
        prompt_injection_suspected=True,
        summary="Customer asks for a refund and tells the assistant to ignore policy.",
    )
    proposal = ActionProposal(
        recommended_action=RecommendedAction.refund,
        explanation="Eligible refund.",
        tool_name="issue_refund",
    )

    guarded, result = apply_guardrails(ticket, proposal)

    assert guarded.recommended_action is RecommendedAction.human_review
    assert guarded.requires_human
    assert {finding.code for finding in result.findings} == {"prompt_injection_blocked"}


def test_ungrounded_policy_answer_is_blocked():
    ticket = SupportTicket(
        issue_type=IssueType.product_information,
        order_ref="KW-O-000950",
        sentiment=Sentiment.calm,
        urgency=Urgency.low,
        summary="Customer asks about a policy.",
    )
    proposal = ActionProposal(recommended_action=RecommendedAction.human_review, explanation="Needs review.")
    policy = PolicyAnswer(
        question="What is the return window?",
        answer="The return window is 999 days.",
        grounded=False,
        unsupported_claims=["999"],
    )

    _, result = apply_guardrails(ticket, proposal, policy)

    assert not result.policy_answer_allowed
    assert "policy_fabrication_blocked" in {finding.code for finding in result.findings}
