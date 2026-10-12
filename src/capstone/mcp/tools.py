"""Shared tool facade for the MCP server and M6 agents."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

from capstone.tools import actions, calculators, lookups
from capstone.tools.errors import ToolError
from capstone.tools.repository import Repository, get_repository


def _tool_result(fn: Callable[[], dict[str, Any] | list[dict[str, Any]]]) -> dict[str, Any]:
    try:
        return {"ok": True, "result": fn()}
    except ToolError as exc:
        return {"ok": False, "error": exc.to_dict()}


class ShopSenseToolGateway:
    """Thin adapter around deterministic M2 mock APIs.

    The same methods are exposed by the MCP server and used by M6 agents, so tool
    behavior stays identical across chat/email/demo entry points.
    """

    def __init__(self, repo: Repository | None = None):
        self.repo = repo or get_repository()

    def get_customer(self, customer_ref: str) -> dict[str, Any]:
        return _tool_result(lambda: lookups.get_customer(self.repo, customer_ref))

    def get_order(self, customer_ref: str, order_ref: str) -> dict[str, Any]:
        return _tool_result(lambda: lookups.get_order(self.repo, customer_ref, order_ref))

    def list_orders(self, customer_ref: str) -> dict[str, Any]:
        return _tool_result(lambda: lookups.list_orders(self.repo, customer_ref))

    def track_shipment(self, customer_ref: str, order_ref: str) -> dict[str, Any]:
        return _tool_result(lambda: lookups.track_shipment(self.repo, customer_ref, order_ref))

    def check_eligibility(
        self,
        customer_ref: str,
        order_ref: str,
        reason_code: str,
        today: str,
    ) -> dict[str, Any]:
        return _tool_result(
            lambda: calculators.check_eligibility(
                self.repo,
                customer_ref,
                order_ref,
                reason_code,
                date.fromisoformat(today),
            )
        )

    def calculate_refund(self, customer_ref: str, order_ref: str, reason_code: str) -> dict[str, Any]:
        return _tool_result(
            lambda: calculators.calculate_refund(self.repo, customer_ref, order_ref, reason_code)
        )

    def required_approver(self, customer_ref: str, amount_inr: float) -> dict[str, Any]:
        return _tool_result(
            lambda: calculators.required_approver(self.repo, customer_ref, amount_inr)
        )

    def issue_refund(
        self,
        customer_ref: str,
        order_ref: str,
        reason_code: str,
        today: str,
        approved_by: str = "auto",
    ) -> dict[str, Any]:
        return _tool_result(
            lambda: actions.issue_refund(
                self.repo,
                customer_ref,
                order_ref,
                reason_code,
                date.fromisoformat(today),
                approved_by,
            )
        )

    def create_replacement(
        self,
        customer_ref: str,
        order_ref: str,
        reason: str,
        today: str,
        approved_by: str = "auto",
    ) -> dict[str, Any]:
        return _tool_result(
            lambda: actions.create_replacement(
                self.repo,
                customer_ref,
                order_ref,
                reason,
                date.fromisoformat(today),
                approved_by,
            )
        )

    def flag_for_human(
        self,
        customer_ref: str,
        order_ref: str | None,
        trigger: str,
        note: str = "",
    ) -> dict[str, Any]:
        return _tool_result(
            lambda: actions.flag_for_human(self.repo, customer_ref, order_ref, trigger, note)
        )

