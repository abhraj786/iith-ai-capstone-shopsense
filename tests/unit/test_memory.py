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
    assert reloaded["memory_types"]["semantic"]
    assert reloaded["memory_types"]["episodic"]
    assert reloaded["memory_types"]["procedural"]
    assert "refund_request x1" in reloaded["rolling_summary"]
    assert "preferred_channel=phone" in reloaded["rolling_summary"]


def test_customer_memory_rolls_up_long_history(tmp_path):
    store = CustomerMemoryStore(tmp_path)
    action = ActionProposal(
        recommended_action=RecommendedAction.human_review,
        requires_human=True,
        tool_name="flag_for_human",
        explanation="Legal escalation.",
    )

    for i in range(7):
        store.append_ticket(
            "KW-C-00285",
            _ticket(order_ref=f"KW-O-{i:06d}"),
            action,
            channel="email",
            received_at=f"2026-03-{10 + i:02d}T15:30",
        )

    context = store.customer_context("KW-C-00285")

    assert context["ticket_count"] == 7
    assert len(context["recent_tickets"]) == 5
    assert "Long-running customer history: 7 recorded tickets" in context["rolling_summary"]
    assert "Latest ticket: refund_request for order KW-O-000006" in context["rolling_summary"]
