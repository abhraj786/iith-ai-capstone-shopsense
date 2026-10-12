"""M6 MCP tool facade tests."""

from capstone.mcp.tools import ShopSenseToolGateway
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

