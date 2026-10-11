"""M3 memory tests."""

from capstone.memory.store import CustomerMemoryStore
from capstone.schemas.actions import ActionProposal, RecommendedAction
from capstone.schemas.intake import IssueType, Sentiment, SupportTicket, Urgency


def _ticket(order_ref="KW-O-000950"):
    return SupportTicket(
        issue_type=IssueType.refund_request,
        order_ref=order_ref,
        sentiment=Sentiment.angry,
        urgency=Urgency.high,
        claimed_amount_inr=6499,
        contact_number=2,
        escalation_signals=[],
        prompt_injection_suspected=False,
        missing_fields=[],
        summary="Customer wants a refund for a late order.",
    )


def test_customer_memory_persists_preferences_and_ticket_history(tmp_path):
    store = CustomerMemoryStore(tmp_path)
    store.remember_preference("KW-C-00285", "preferred_channel", "phone")
    action = ActionProposal(
        recommended_action=RecommendedAction.human_review,
        requires_human=True,
        tool_name="flag_for_human",
        explanation="Legal escalation.",
    )
    store.append_ticket("KW-C-00285", _ticket(), action, channel="email",
                        received_at="2026-03-10T15:30")

    reloaded = CustomerMemoryStore(tmp_path).customer_context("KW-C-00285")
    assert reloaded["preferences"]["preferred_channel"] == "phone"
    assert reloaded["ticket_count"] == 1
    assert reloaded["recent_tickets"][0]["recommended_action"] == "human_review"
