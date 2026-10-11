"""Deterministic policy calculations: eligibility, refund amount, approval tier (M2).

All thresholds come from the policy tables, never from constants here. `today` is a
parameter because the seed data is dated; callers pass a fixed date for reproducibility.
"""

from datetime import date, datetime, timedelta

from capstone.tools.errors import ToolError
from capstone.tools.lookups import get_customer, get_order
from capstone.tools.repository import Repository

REASON_CODES = {
    "damaged", "wrong_item", "quality", "not_delivered",
    "late_delivery", "changed_mind", "cancelled_before_dispatch",
}


def _limit(repo: Repository, name: str) -> float:
    return float(repo.get("policy_limits", limit=name)["value"])


def _placed_on(order: dict) -> date:
    return datetime.fromisoformat(order["placed_at"]).date()


def delivered_on(order: dict) -> date | None:
    if order["status"] not in ("delivered", "returned") or not order["actual_delivery_days"]:
        return None
    return _placed_on(order) + timedelta(days=int(order["actual_delivery_days"]))


def check_eligibility(repo: Repository, customer_ref: str, order_ref: str,
                      reason_code: str, today: date) -> dict:
    if reason_code not in REASON_CODES:
        raise ToolError("invalid_reason", f"Unknown reason_code {reason_code}")
    order = get_order(repo, customer_ref, order_ref)
    category = repo.get("category_policies", category=order["category"])
    delivered = delivered_on(order)
    since = (today - delivered).days if delivered else None

    def result(eligible: bool, why: str, **extra) -> dict:
        return {"order_ref": order_ref, "reason_code": reason_code,
                "eligible": eligible, "why": why, **extra}

    status = order["status"]
    if reason_code == "cancelled_before_dispatch":
        ok = status == "placed"
        return result(ok, "Order has not shipped" if ok else f"Order is already {status}")

    if status == "delivered" and delivered is None:
        # Seed data has delivered orders with no delivery date; never guess a window from it.
        return result(False, "No delivery date on record for this order", needs_human=True)

    if reason_code == "not_delivered":
        if status == "shipped":
            due = _placed_on(order) + timedelta(days=int(order["delivery_promise_days"]))
            overdue = (today - due).days
            limit = int(_limit(repo, "lost_in_transit_days"))
            ok = overdue >= limit
            return result(ok, f"{overdue} days past promised date; lost after {limit}")
        if delivered:
            limit = int(_limit(repo, "delivery_dispute_report_days"))
            ok = since <= limit
            return result(ok, f"Delivered {since} days ago; disputes allowed within {limit}",
                          needs_dispute_investigation=ok)
        return result(False, f"Order is {status}")

    if status != "delivered":
        return result(False, f"Order is {status}, not delivered")

    if reason_code == "late_delivery":
        late = int(order["actual_delivery_days"]) > int(order["delivery_promise_days"])
        return result(late, "Delivered after the promised date" if late else "Delivered on time")

    if reason_code == "changed_mind":
        window = category["return_window_days"]
        if not window:
            return result(False, f"{order['category']} is not returnable for change of mind")
        window = int(window)
        ok = since <= window
        return result(ok, f"Delivered {since} days ago; {order['category']} window is {window}",
                      window_days=window)

    # damaged / wrong_item / quality are defect claims
    window = int(category["defect_claim_days"])
    ok = since <= window
    return result(ok, f"Delivered {since} days ago; {order['category']} defect claims within {window}",
                  window_days=window)


def calculate_refund(repo: Repository, customer_ref: str, order_ref: str, reason_code: str) -> dict:
    """Refund amount in INR after restocking fee and customer-paid pickup, per category policy."""
    order = get_order(repo, customer_ref, order_ref)
    rule = repo.get("refund_rules", reason_code=reason_code)
    if not rule:
        raise ToolError("invalid_reason", f"Unknown reason_code {reason_code}")
    category = repo.get("category_policies", category=order["category"])
    value = float(order["order_value_inr"])

    gross = value * float(rule["refund_pct"]) / 100
    restocking = 0.0
    if rule["restocking_fee_applies"] == "True":
        restocking = value * float(category["restocking_fee_pct"] or 0) / 100
    pickup = 0.0
    if rule["return_shipping_paid_by"] == "customer":
        pickup = float(category["return_pickup_fee_inr"] or 0)
    amount = max(round(gross - restocking - pickup), 0)
    return {
        "order_ref": order_ref, "reason_code": reason_code, "order_value_inr": value,
        "gross_inr": round(gross), "restocking_fee_inr": round(restocking),
        "pickup_fee_inr": round(pickup), "refund_inr": amount,
        "return_required": rule["return_required"] == "True",
    }


def required_approver(repo: Repository, customer_ref: str, amount_inr: float) -> dict:
    """Lowest approver allowed to approve `amount_inr`. 'auto' only if the account permits it."""
    customer = get_customer(repo, customer_ref)
    blocked = (
        customer.get("automated_refunds_allowed") == "False"
        or customer.get("flagged_for_abuse") == "True"
        or customer.get("serial_refund_requester") == "True"
    )
    approvers = repo.rows("refund_authority")
    ranked = sorted(approvers, key=lambda a: float(a["max_refund_inr"] or "inf"))
    for a in ranked:
        if a["approver"] == "auto" and blocked:
            continue
        if float(a["max_refund_inr"] or "inf") >= amount_inr:
            return {"approver": a["approver"], "is_human": a["is_human"] == "True",
                    "account_restricted": blocked}
    raise ToolError("no_approver", f"No approver can authorise {amount_inr}")
