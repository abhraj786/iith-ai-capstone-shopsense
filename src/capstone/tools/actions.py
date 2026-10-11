"""Simulated side effects with authorization limits, enforced here and not in prompts (M2).

Every action is idempotent: retrying (or resuming a workflow after a crash) returns the
original result instead of acting twice. `approved_by` names the approver tier. The agent
itself is only ever allowed 'auto'; higher tiers are supplied by the human-approval step (M5).
"""

from datetime import date

from capstone.tools.calculators import calculate_refund, check_eligibility, required_approver
from capstone.tools.errors import ToolError
from capstone.tools.lookups import get_order
from capstone.tools.repository import Repository

REPLACEMENT_REASONS = {"damaged", "wrong_item", "quality"}


def _check_approver(repo: Repository, customer_ref: str, approved_by: str, amount: float) -> None:
    needed = required_approver(repo, customer_ref, amount)
    tiers = {a["approver"]: a for a in repo.rows("refund_authority")}
    if approved_by not in tiers:
        raise ToolError("unknown_approver", f"Unknown approver {approved_by}")
    limit = float(tiers[approved_by]["max_refund_inr"] or "inf")
    blocked_auto = approved_by == "auto" and needed["account_restricted"]
    if limit < amount or blocked_auto:
        raise ToolError(
            "approval_required",
            f"{amount:.0f} INR needs approval by {needed['approver']} (requested: {approved_by})",
        )


def issue_refund(repo: Repository, customer_ref: str, order_ref: str, reason_code: str,
                 today: date, approved_by: str = "auto") -> dict:
    key = f"refund:{order_ref}"
    if done := repo.ledger_get(key):
        return {**done, "duplicate": True}

    eligibility = check_eligibility(repo, customer_ref, order_ref, reason_code, today)
    if not eligibility["eligible"]:
        raise ToolError("not_eligible", eligibility["why"])
    existing = [r for r in repo.find("refunds", order_ref=order_ref) if r["status"] != "rejected"]
    if existing:
        return {"refund_id": existing[0]["refund_id"], "duplicate": True,
                "amount_inr": float(existing[0]["amount_inr"])}

    amount = calculate_refund(repo, customer_ref, order_ref, reason_code)["refund_inr"]
    _check_approver(repo, customer_ref, approved_by, amount)

    refund_id = repo.next_id("refunds", "refund_id", "KW-RF", 5)
    repo.append("refunds", {
        "refund_id": refund_id, "order_ref": order_ref, "amount_inr": amount,
        "reason_code": reason_code, "status": "approved", "approved_by": approved_by,
        "requested_on": today.isoformat(),
    })
    result = {"refund_id": refund_id, "order_ref": order_ref, "amount_inr": amount,
              "status": "approved", "approved_by": approved_by, "duplicate": False}
    repo.ledger_put(key, result)
    return result


def create_replacement(repo: Repository, customer_ref: str, order_ref: str, reason: str,
                       today: date, approved_by: str = "auto") -> dict:
    key = f"replacement:{order_ref}"
    if done := repo.ledger_get(key):
        return {**done, "duplicate": True}
    if reason not in REPLACEMENT_REASONS:
        raise ToolError("invalid_reason", f"Replacements are only for {sorted(REPLACEMENT_REASONS)}")

    eligibility = check_eligibility(repo, customer_ref, order_ref, reason, today)
    if not eligibility["eligible"]:
        raise ToolError("not_eligible", eligibility["why"])
    existing = [r for r in repo.find("replacements", order_ref=order_ref)
                if r["status"] != "rejected"]
    if existing:
        return {"replacement_id": existing[0]["replacement_id"], "duplicate": True}

    value = float(get_order(repo, customer_ref, order_ref)["order_value_inr"])
    _check_approver(repo, customer_ref, approved_by, value)

    replacement_id = repo.next_id("replacements", "replacement_id", "KW-RP", 5)
    repo.append("replacements", {
        "replacement_id": replacement_id, "order_ref": order_ref, "reason": reason,
        "requested_on": today.isoformat(), "status": "approved", "approved_by": approved_by,
    })
    result = {"replacement_id": replacement_id, "order_ref": order_ref, "status": "approved",
              "approved_by": approved_by, "duplicate": False}
    repo.ledger_put(key, result)
    return result


def flag_for_human(repo: Repository, customer_ref: str, order_ref: str | None,
                   trigger: str, note: str = "") -> dict:
    """Queue a case for a human. `trigger` must be a known escalation trigger."""
    row = repo.get("escalation_triggers", trigger=trigger)
    if not row:
        raise ToolError("unknown_trigger", f"Unknown trigger {trigger}")
    if order_ref:
        get_order(repo, customer_ref, order_ref)  # a customer can't queue someone else's order
    key = f"queue:{customer_ref}:{order_ref}:{trigger}"
    if done := repo.ledger_get(key):
        return {**done, "duplicate": True}
    queue_id = repo.next_id("human_queue", "queue_id", "KW-HQ", 5)
    repo.append("human_queue", {"queue_id": queue_id, "customer_ref": customer_ref,
                                "order_ref": order_ref or "", "trigger": trigger, "note": note})
    result = {"queue_id": queue_id, "routes_to": row["routes_to"], "duplicate": False}
    repo.ledger_put(key, result)
    return result
