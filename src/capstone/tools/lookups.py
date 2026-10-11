"""Read-only lookups. Every order access is scoped to the requesting customer (M2)."""

from capstone.tools.errors import ToolError
from capstone.tools.repository import Repository


def get_customer(repo: Repository, customer_ref: str) -> dict:
    customer = repo.get("customers", customer_ref=customer_ref)
    if not customer:
        raise ToolError("customer_not_found", f"No customer {customer_ref}")
    profile = repo.get("customer_profiles", customer_ref=customer_ref) or {}
    return {**customer, **{k: v for k, v in profile.items() if k != "customer_ref"}}


def get_order(repo: Repository, customer_ref: str, order_ref: str) -> dict:
    """Return the order with its product and category. Unknown orders and orders belonging
    to another customer give the same error, so existence is not leaked across customers."""
    order = repo.get("orders", order_ref=order_ref)
    if not order or order["customer_ref"] != customer_ref:
        raise ToolError("order_not_found", f"No order {order_ref} for this customer")
    product = repo.get("products", sku=order["sku"]) or {}
    return {**order, "product_title": product.get("title"), "category": product.get("category")}


def list_orders(repo: Repository, customer_ref: str) -> list[dict]:
    return [
        {k: o[k] for k in ("order_ref", "sku", "order_value_inr", "placed_at", "status")}
        for o in repo.find("orders", customer_ref=customer_ref)
    ]


def track_shipment(repo: Repository, customer_ref: str, order_ref: str) -> dict:
    order = get_order(repo, customer_ref, order_ref)
    shipment = repo.get("shipments", order_ref=order_ref)
    if not shipment:
        return {
            "order_ref": order_ref,
            "order_status": order["status"],
            "shipment": None,
            "note": "No shipment yet",
        }
    return {"order_ref": order_ref, "order_status": order["status"], "shipment": shipment}
