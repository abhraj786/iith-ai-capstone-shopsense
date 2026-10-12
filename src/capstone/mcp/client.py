"""Small MCP stdio client for ShopSense tool calls."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from capstone.settings import PROJECT_ROOT


class ShopSenseMCPClient:
    """Call the ShopSense MCP server over stdio.

    This is intentionally thin: the server remains the tool authority, while the
    client only handles process startup, discovery, invocation, and result parsing.
    """

    def __init__(
        self,
        *,
        command: str | None = None,
        args: list[str] | None = None,
        cwd: Path | str | None = None,
        env: dict[str, str] | None = None,
    ):
        self.command = command or sys.executable
        self.args = args or ["-m", "capstone.mcp.server"]
        self.cwd = str(cwd or PROJECT_ROOT)
        self.env = env

    def list_tools(self) -> list[str]:
        return anyio.run(self._list_tools)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return anyio.run(self._call_tool, name, arguments)

    async def _list_tools(self) -> list[str]:
        async with self._session() as session:
            tools = await session.list_tools()
            return [tool.name for tool in tools.tools]

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        async with self._session() as session:
            result = await session.call_tool(name, arguments)
            if result.structuredContent is not None:
                return {**result.structuredContent, "transport": "mcp"}
            if result.isError:
                return {"ok": False, "transport": "mcp", "error": {"error": "mcp_tool_error"}}
            return {"ok": True, "transport": "mcp", "result": {}}

    def _session(self):
        params = StdioServerParameters(
            command=self.command,
            args=self.args,
            cwd=self.cwd,
            env=self.env,
        )
        return _MCPClientSession(params)


class _MCPClientSession:
    def __init__(self, params: StdioServerParameters):
        self.params = params
        self._stdio_cm = None
        self._session_cm = None
        self.session = None

    async def __aenter__(self) -> ClientSession:
        self._stdio_cm = stdio_client(self.params)
        read, write = await self._stdio_cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self.session = await self._session_cm.__aenter__()
        await self.session.initialize()
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session_cm is not None:
            await self._session_cm.__aexit__(exc_type, exc, tb)
        if self._stdio_cm is not None:
            await self._stdio_cm.__aexit__(exc_type, exc, tb)


class MCPShopSenseToolGateway:
    """Gateway with the same method surface as `ShopSenseToolGateway`, backed by MCP."""

    def __init__(self, client: ShopSenseMCPClient | None = None):
        self.client = client or ShopSenseMCPClient()

    def get_customer(self, customer_ref: str) -> dict[str, Any]:
        return self.client.call_tool("get_customer", {"customer_ref": customer_ref})

    def get_order(self, customer_ref: str, order_ref: str) -> dict[str, Any]:
        return self.client.call_tool("get_order", {"customer_ref": customer_ref, "order_ref": order_ref})

    def list_orders(self, customer_ref: str) -> dict[str, Any]:
        return self.client.call_tool("list_orders", {"customer_ref": customer_ref})

    def track_shipment(self, customer_ref: str, order_ref: str) -> dict[str, Any]:
        return self.client.call_tool("track_shipment", {"customer_ref": customer_ref, "order_ref": order_ref})

    def check_eligibility(
        self,
        customer_ref: str,
        order_ref: str,
        reason_code: str,
        today: str,
    ) -> dict[str, Any]:
        return self.client.call_tool(
            "check_eligibility",
            {
                "customer_ref": customer_ref,
                "order_ref": order_ref,
                "reason_code": reason_code,
                "today": today,
            },
        )

    def calculate_refund(self, customer_ref: str, order_ref: str, reason_code: str) -> dict[str, Any]:
        return self.client.call_tool(
            "calculate_refund",
            {"customer_ref": customer_ref, "order_ref": order_ref, "reason_code": reason_code},
        )

    def required_approver(self, customer_ref: str, amount_inr: float) -> dict[str, Any]:
        return self.client.call_tool(
            "required_approver",
            {"customer_ref": customer_ref, "amount_inr": amount_inr},
        )

    def issue_refund(
        self,
        customer_ref: str,
        order_ref: str,
        reason_code: str,
        today: str,
        approved_by: str = "auto",
    ) -> dict[str, Any]:
        return self.client.call_tool(
            "issue_refund",
            {
                "customer_ref": customer_ref,
                "order_ref": order_ref,
                "reason_code": reason_code,
                "today": today,
                "approved_by": approved_by,
            },
        )

    def create_replacement(
        self,
        customer_ref: str,
        order_ref: str,
        reason: str,
        today: str,
        approved_by: str = "auto",
    ) -> dict[str, Any]:
        return self.client.call_tool(
            "create_replacement",
            {
                "customer_ref": customer_ref,
                "order_ref": order_ref,
                "reason": reason,
                "today": today,
                "approved_by": approved_by,
            },
        )

    def flag_for_human(
        self,
        customer_ref: str,
        order_ref: str | None,
        trigger: str,
        note: str = "",
    ) -> dict[str, Any]:
        return self.client.call_tool(
            "flag_for_human",
            {"customer_ref": customer_ref, "order_ref": order_ref, "trigger": trigger, "note": note},
        )

