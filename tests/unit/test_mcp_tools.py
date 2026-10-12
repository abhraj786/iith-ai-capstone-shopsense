"""M6 MCP tool facade tests."""

from capstone.mcp.tools import ShopSenseToolGateway
from capstone.mcp.client import MCPShopSenseToolGateway, ShopSenseMCPClient
from capstone.settings import get_settings
from capstone.tools.repository import Repository


def test_mcp_gateway_scopes_order_access_to_customer(tmp_path):
    repo = Repository(get_settings().seed_dir, tmp_path / "state")
    gateway = ShopSenseToolGateway(repo)
    order = repo.rows("orders")[0]

    ok = gateway.get_order(order["customer_ref"], order["order_ref"])
    assert ok["ok"]
    assert ok["result"]["order_ref"] == order["order_ref"]

    denied = gateway.get_order("KW-C-DOES-NOT-OWN", order["order_ref"])
    assert not denied["ok"]
    assert denied["error"]["error"] == "order_not_found"


def test_mcp_gateway_exposes_refund_calculator(tmp_path):
    repo = Repository(get_settings().seed_dir, tmp_path / "state")
    gateway = ShopSenseToolGateway(repo)
    delivered = next(row for row in repo.rows("orders") if row["status"] == "delivered")

    result = gateway.calculate_refund(
        delivered["customer_ref"],
        delivered["order_ref"],
        "late_delivery",
    )

    assert result["ok"]
    assert result["result"]["order_ref"] == delivered["order_ref"]
    assert result["result"]["refund_inr"] >= 0


def test_mcp_client_discovers_and_calls_server_tool(tmp_path):
    client = ShopSenseMCPClient(env={"CAPSTONE_RUNTIME_ROOT": str(tmp_path / "runtime")})

    tools = client.list_tools()
    assert "track_shipment" in tools
    assert "issue_refund" in tools

    gateway = MCPShopSenseToolGateway(client)
    result = gateway.track_shipment("KW-C-00285", "KW-O-000950")

    assert result["ok"]
    assert result["transport"] == "mcp"
    assert result["result"]["order_ref"] == "KW-O-000950"

