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


def _event_ticket(i, summary):
    t = _ticket(order_ref=f"KW-O-00000{i}")
    t.summary = summary
    return t


def test_old_tickets_are_condensed_with_previous_summary_and_recent_stay_verbatim(tmp_path):
    seen = []

    def fake_summarizer(events, previous):
        seen.append(([e["summary"] for e in events], previous))
        return (previous + " | " if previous else "") + "; ".join(e["summary"] for e in events)

    store = CustomerMemoryStore(tmp_path, summarizer=fake_summarizer)
    store.append_ticket("C1", _event_ticket(1, "Deliver to the back gate, allergic to peanuts."))
    for i in range(2, 9):
        store.append_ticket("C1", _event_ticket(i, f"Package {i} late."))

    ctx = store.customer_context("C1")
    assert "back gate" in ctx["rolling_summary"] and "peanuts" in ctx["rolling_summary"]
    assert [e["summary"] for e in ctx["recent_tickets"]] == [f"Package {i} late." for i in range(4, 9)]
    # each old ticket is summarized once, and the previous summary is handed back in
    assert [batch for batch, _ in seen] == [
        ["Deliver to the back gate, allergic to peanuts."], ["Package 2 late."], ["Package 3 late."]]
    assert "back gate" in seen[1][1]
    assert len(store.load("C1")["tickets"]) == 8  # raw history is never discarded


def test_summarizer_failure_never_blocks_a_ticket_and_is_retried(tmp_path):
    calls = {"n": 0}

    def flaky(events, previous):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("llm down")
        return "caught up: " + "; ".join(e["summary"] for e in events)

    store = CustomerMemoryStore(tmp_path, summarizer=flaky)
    for i in range(1, 8):
        store.append_ticket("C2", _event_ticket(i, f"Issue {i}."))
    mem = store.load("C2")
    assert len(mem["tickets"]) == 7
    assert "Issue 1." in mem["history_summary"] and "Issue 2." in mem["history_summary"]
    assert mem["summarized_upto"] == 2


def test_prior_contacts_counts_same_order_and_issue_and_ignores_replays(tmp_path):
    store = CustomerMemoryStore(tmp_path)
    t = _ticket("KW-O-000777")
    for day in ("2026-07-01", "2026-07-02", "2026-07-02"):  # last one is an exact replay
        store.append_ticket("C3", t, received_at=day)
    store.append_ticket("C3", _ticket("KW-O-000888"), received_at="2026-07-03")  # other order
    assert store.prior_contacts("C3", "KW-O-000777", "refund_request") == 2
    # the current message's own date and channel are not a prior contact (replay-safe)
    assert store.prior_contacts("C3", "KW-O-000777", "refund_request", "2026-07-02", None) == 1
    assert store.prior_contacts("C3", "KW-O-000777", "missing_item") == 0
    assert store.prior_contacts("C3", None, "refund_request") == 0
    assert store.prior_contacts("new-customer", "KW-O-000777", "refund_request") == 0
