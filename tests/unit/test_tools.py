"""M2 tool tests: deterministic, run against the generated seed tables with a temp runtime."""

from datetime import timedelta

import pytest

from capstone.settings import get_settings
from capstone.tools import actions, calculators, lookups
from capstone.tools.calculators import delivered_on
from capstone.tools.errors import ToolError
from capstone.tools.repository import Repository


@pytest.fixture
def repo(tmp_path):
    seed = get_settings().seed_dir
    if not seed.exists():
        pytest.skip("generate the ShopSense tables first (see README)")
    return Repository(seed, tmp_path / "state")


def _delivered(repo, *, category=None, min_value=0, max_value=10**9):
    """A delivered order with no existing refund/replacement, from a normal account."""
    refunded = {r["order_ref"] for r in repo.rows("refunds") + repo.rows("replacements")}
    restricted = {c["customer_ref"] for c in repo.rows("customer_profiles")
                  if c["automated_refunds_allowed"] == "False"
                  or c["serial_refund_requester"] == "True"
                  or c["over_return_rate_threshold"] == "True"}
    for o in repo.rows("orders"):
        order = lookups.get_order(repo, o["customer_ref"], o["order_ref"])
        if (o["status"] == "delivered" and o["actual_delivery_days"]
                and o["order_ref"] not in refunded
                and o["customer_ref"] not in restricted
                and (category is None or order["category"] == category)
                and min_value <= float(o["order_value_inr"]) <= max_value):
            return order
    pytest.skip("no suitable order in this data snapshot")


def test_customer_cannot_read_another_customers_order(repo):
    order = repo.rows("orders")[0]
    other = next(c["customer_ref"] for c in repo.rows("customers")
                 if c["customer_ref"] != order["customer_ref"])
    with pytest.raises(ToolError) as e:
        lookups.get_order(repo, other, order["order_ref"])
    assert e.value.code == "order_not_found"
    with pytest.raises(ToolError) as e2:  # same error as a genuinely missing order
        lookups.get_order(repo, other, "KW-O-999999")
    assert e.value.message.split(" for ")[0].split()[0:2] == e2.value.message.split(" for ")[0].split()[0:2]


def test_change_of_mind_window_uses_category_policy(repo):
    order = _delivered(repo, category="Electronics")
    c, ref = order["customer_ref"], order["order_ref"]
    d = delivered_on(order)
    assert calculators.check_eligibility(repo, c, ref, "changed_mind", d + timedelta(days=15))["eligible"]
    assert not calculators.check_eligibility(repo, c, ref, "changed_mind", d + timedelta(days=16))["eligible"]


def test_groceries_not_returnable_for_change_of_mind(repo):
    order = _delivered(repo, category="Groceries")
    r = calculators.check_eligibility(repo, order["customer_ref"], order["order_ref"],
                                      "changed_mind", delivered_on(order))
    assert not r["eligible"]


def test_changed_mind_refund_deducts_restocking_and_pickup(repo):
    order = _delivered(repo, category="Electronics")
    r = calculators.calculate_refund(repo, order["customer_ref"], order["order_ref"], "changed_mind")
    value = float(order["order_value_inr"])
    assert r["refund_inr"] == max(round(value - value * 0.15 - 99), 0)


def test_damaged_item_refunded_in_full(repo):
    order = _delivered(repo)
    r = calculators.calculate_refund(repo, order["customer_ref"], order["order_ref"], "damaged")
    assert r["refund_inr"] == round(float(order["order_value_inr"]))


def test_refund_over_auto_cap_needs_human_approval(repo):
    order = _delivered(repo, min_value=2001)
    c, ref, today = order["customer_ref"], order["order_ref"], delivered_on(order)
    with pytest.raises(ToolError) as e:
        actions.issue_refund(repo, c, ref, "quality", today, approved_by="auto")
    assert e.value.code == "approval_required"
    assert not [r for r in repo.find("refunds", order_ref=ref)]  # nothing was written


def test_refund_within_cap_is_auto_approved(repo):
    order = _delivered(repo, max_value=2000)
    c, ref, today = order["customer_ref"], order["order_ref"], delivered_on(order)
    result = actions.issue_refund(repo, c, ref, "quality", today)
    assert result["status"] == "approved" and not result["duplicate"]


def test_retry_does_not_refund_twice(repo):
    order = _delivered(repo, max_value=2000)
    c, ref, today = order["customer_ref"], order["order_ref"], delivered_on(order)
    first = actions.issue_refund(repo, c, ref, "quality", today)
    again = actions.issue_refund(repo, c, ref, "quality", today)
    assert again["duplicate"] and again["refund_id"] == first["refund_id"]
    assert len(repo.find("refunds", order_ref=ref)) == 1


def test_human_tier_can_approve_large_refund(repo):
    order = _delivered(repo, min_value=2001, max_value=10000)
    c, ref, today = order["customer_ref"], order["order_ref"], delivered_on(order)
    result = actions.issue_refund(repo, c, ref, "quality", today, approved_by="team_lead")
    assert result["approved_by"] == "team_lead"


def test_refund_for_ineligible_reason_is_rejected(repo):
    order = _delivered(repo)  # delivered on time or not, but never 'cancelled before dispatch'
    with pytest.raises(ToolError) as e:
        actions.issue_refund(repo, order["customer_ref"], order["order_ref"],
                             "cancelled_before_dispatch", delivered_on(order))
    assert e.value.code == "not_eligible"


def test_flag_for_human_is_idempotent_and_validates_trigger(repo):
    order = repo.rows("orders")[0]
    c, ref = order["customer_ref"], order["order_ref"]
    a = actions.flag_for_human(repo, c, ref, "legal_or_regulatory", "mentioned consumer forum")
    b = actions.flag_for_human(repo, c, ref, "legal_or_regulatory", "mentioned consumer forum")
    assert a["routes_to"] == "legal_desk" and b["duplicate"] and a["queue_id"] == b["queue_id"]
    with pytest.raises(ToolError):
        actions.flag_for_human(repo, c, ref, "made_up_trigger")


def test_delivered_order_without_delivery_date_goes_to_a_human(repo):
    o = next(o for o in repo.rows("orders")
             if o["status"] == "delivered" and not o["actual_delivery_days"])
    today = delivered_on({**o, "actual_delivery_days": "0"})
    for reason in ("damaged", "late_delivery", "changed_mind", "not_delivered"):
        r = calculators.check_eligibility(repo, o["customer_ref"], o["order_ref"], reason, today)
        assert not r["eligible"] and r["needs_human"]


def test_seed_tables_are_never_modified(repo):
    before = (repo.seed_dir / "refunds.csv").read_text()
    order = _delivered(repo, max_value=2000)
    actions.issue_refund(repo, order["customer_ref"], order["order_ref"], "quality", delivered_on(order))
    assert (repo.seed_dir / "refunds.csv").read_text() == before
