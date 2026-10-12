"""MCP server exposing ShopSense mock order/refund/shipping APIs."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from capstone.mcp.tools import ShopSenseToolGateway


mcp = FastMCP("shopsense-order-tools")
gateway = ShopSenseToolGateway()


@mcp.tool()
def get_customer(customer_ref: str) -> dict[str, Any]:
    """Return a customer profile by customer reference."""
    return gateway.get_customer(customer_ref)


@mcp.tool()
def get_order(customer_ref: str, order_ref: str) -> dict[str, Any]:
    """Return an order only when it belongs to the requesting customer."""
    return gateway.get_order(customer_ref, order_ref)


@mcp.tool()
def list_orders(customer_ref: str) -> dict[str, Any]:
    """List orders for one customer."""
    return gateway.list_orders(customer_ref)


@mcp.tool()
def track_shipment(customer_ref: str, order_ref: str) -> dict[str, Any]:
    """Return shipment tracking status for a customer-scoped order."""
    return gateway.track_shipment(customer_ref, order_ref)


@mcp.tool()
def check_eligibility(
    customer_ref: str,
    order_ref: str,
    reason_code: str,
    today: str,
) -> dict[str, Any]:
    """Check refund/replacement eligibility for a reason code."""
    return gateway.check_eligibility(customer_ref, order_ref, reason_code, today)


@mcp.tool()
def calculate_refund(customer_ref: str, order_ref: str, reason_code: str) -> dict[str, Any]:
    """Calculate policy-backed refund amount."""
    return gateway.calculate_refund(customer_ref, order_ref, reason_code)


@mcp.tool()
def required_approver(customer_ref: str, amount_inr: float) -> dict[str, Any]:
    """Return the lowest approval tier for a refund amount."""
    return gateway.required_approver(customer_ref, amount_inr)


@mcp.tool()
def issue_refund(
    customer_ref: str,
    order_ref: str,
    reason_code: str,
    today: str,
    approved_by: str = "auto",
) -> dict[str, Any]:
    """Create an idempotent mock refund when policy and approval permit it."""
    return gateway.issue_refund(customer_ref, order_ref, reason_code, today, approved_by)


@mcp.tool()
def create_replacement(
    customer_ref: str,
    order_ref: str,
    reason: str,
    today: str,
    approved_by: str = "auto",
) -> dict[str, Any]:
    """Create an idempotent mock replacement when policy and approval permit it."""
    return gateway.create_replacement(customer_ref, order_ref, reason, today, approved_by)


@mcp.tool()
def flag_for_human(
    customer_ref: str,
    order_ref: str | None,
    trigger: str,
    note: str = "",
) -> dict[str, Any]:
    """Queue a case for human review."""
    return gateway.flag_for_human(customer_ref, order_ref, trigger, note)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

