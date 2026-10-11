"""M2 agent tests: parsed intake tickets become safe action proposals."""

from datetime import timedelta

import pytest

from capstone.agents.action_agent import plan_action
from capstone.schemas.actions import RecommendedAction
from capstone.schemas.intake import EscalationSignal, IssueType, Sentiment, SupportTicket, Urgency
from capstone.settings import get_settings
from capstone.tools import lookups
from capstone.tools.calculators import delivered_on
from capstone.tools.repository import Repository


@pytest.fixture
def repo(tmp_path):
    return Repository(get_settings().seed_dir, tmp_path / "state")


def ticket(**overrides):
    base = {
        "issue_type": IssueType.refund_request,
        "order_ref": "KW-O-000000",
        "sentiment": Sentiment.calm,
        "urgency": Urgency.normal,
        "claimed_amount_inr": None,
        "contact_number": 1,
        "escalation_signals": [],
        "prompt_injection_suspected": False,
        "missing_fields": [],
        "summary": "Customer needs help with an order.",
    }
    return SupportTicket(**{**base, **overrides})


def _delivered_order(repo, *, max_value=2000, min_value=0, category=None, exclude_refunded=True):
    refunded = {r["order_ref"] for r in repo.rows("refunds")}
    restricted = {c["customer_ref"] for c in repo.rows("customer_profiles")
                  if c["automated_refunds_allowed"] == "False"
                  or c["serial_refund_requester"] == "True"}
    for raw in repo.rows("orders"):
        order = lookups.get_order(repo, raw["customer_ref"], raw["order_ref"])
        if (raw["status"] == "delivered" and raw["actual_delivery_days"]
                and (not exclude_refunded or raw["order_ref"] not in refunded)
                and raw["customer_ref"] not in restricted
                and min_value <= float(raw["order_value_inr"]) <= max_value
                and (category is None or order["category"] == category)):
            return order
    pytest.skip("no suitable delivered order in seed data")


def test_missing_order_ref_requests_missing_info(repo):
    proposal = plan_action(repo, ticket(order_ref=None, missing_fields=["order_ref"]),
                           "KW-C-00317", today=delivered_on(repo.rows("orders")[0]))
    assert proposal.recommended_action is RecommendedAction.request_missing_info
    assert not proposal.executed


def test_track_order_uses_read_only_lookup(repo):
    order = repo.rows("orders")[0]
    proposal = plan_action(repo, ticket(issue_type=IssueType.track_order, order_ref=order["order_ref"]),
                           order["customer_ref"], today=delivered_on(order) or delivered_on({**order, "actual_delivery_days": "0"}))
    assert proposal.recommended_action is RecommendedAction.track_order
    assert proposal.tool_name == "track_shipment"
    assert proposal.tool_result["order_ref"] == order["order_ref"]


def test_legal_signal_routes_to_human_and_can_queue(repo):
    order = repo.rows("orders")[0]
    proposal = plan_action(
        repo,
        ticket(order_ref=order["order_ref"], escalation_signals=[EscalationSignal.legal_or_regulatory]),
        order["customer_ref"],
        today=delivered_on(order) or delivered_on({**order, "actual_delivery_days": "0"}),
        execute=True,
    )
    assert proposal.recommended_action is RecommendedAction.human_review
    assert proposal.requires_human and proposal.executed
    assert proposal.tool_result["routes_to"] == "legal_desk"


def test_small_refund_is_only_proposed_until_execute_true(repo):
    order = _delivered_order(repo, max_value=4000, category="Furniture")
    today = delivered_on(order) + timedelta(days=1)
    proposal = plan_action(repo, ticket(issue_type=IssueType.return_request, order_ref=order["order_ref"]),
                           order["customer_ref"], today=today)
    assert proposal.recommended_action is RecommendedAction.refund
    assert not proposal.executed
    assert not repo.find("refunds", order_ref=order["order_ref"])

    executed = plan_action(repo, ticket(issue_type=IssueType.return_request, order_ref=order["order_ref"]),
                           order["customer_ref"], today=today, execute=True)
    assert executed.executed and executed.tool_result["status"] == "approved"
    assert len(repo.find("refunds", order_ref=order["order_ref"])) == 1


def test_large_refund_routes_to_refund_approver(repo):
    order = _delivered_order(repo, min_value=2001, max_value=10**9, exclude_refunded=False)
    proposal = plan_action(repo, ticket(order_ref=order["order_ref"]),
                           order["customer_ref"], today=delivered_on(order) + timedelta(days=1))
    assert proposal.recommended_action is RecommendedAction.human_review
    assert proposal.requires_human
    assert proposal.tool_args["trigger"] == "refund_above_auto_cap"


def test_wrong_customer_order_does_not_leak_or_execute(repo):
    order = repo.rows("orders")[0]
    other_customer = next(c["customer_ref"] for c in repo.rows("customers")
                          if c["customer_ref"] != order["customer_ref"])
    proposal = plan_action(repo, ticket(order_ref=order["order_ref"]),
                           other_customer, today=delivered_on(order) or delivered_on({**order, "actual_delivery_days": "0"}),
                           execute=True)
    assert proposal.recommended_action is RecommendedAction.human_review
    assert proposal.tool_error["error"] == "order_not_found"
    assert not proposal.executed
