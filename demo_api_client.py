"""Exercise the running ShopSense API from the command line.

Usage:
  python -m uvicorn capstone.api:app --port 8000
  python demo_api_client.py
  python demo_api_client.py --url https://your-ngrok-url.ngrok-free.app

By default this sends parsed SupportTicket objects from the M8 golden set, so
the demo is deterministic and does not require an LLM key. Pass --live to send
only raw text and exercise the full M1 LLM parsing path.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
GOLDEN_PATH = ROOT / "data" / "shopsense" / "eval" / "golden_m8_tickets.json"

CASE_IDS = [
    ("legal high refund", "M8-05-legal-large-refund"),
    ("prompt injection", "M8-06-injection-ignore-instructions"),
    ("missing order", "M8-11-missing-order-tracking"),
    ("order status", "M8-01-track-calm"),
    ("product safety", "M8-13-product-safety"),
    ("over-cap refund", "M8-04-angry-large-refund"),
    ("warranty question", "M8-18-warranty-claim"),
]


def call(url: str, payload: dict[str, Any] | None = None, timeout: float = 120.0) -> tuple[int, dict[str, Any]]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raw = exc.read() or b"{}"
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"raw": raw.decode("utf-8", "replace")[:1000]}
    except (TimeoutError, socket.timeout):
        return 0, {"error": f"no answer within {timeout:.0f}s"}
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        print(f"Cannot reach {url}: {reason}. Is the API running?", file=sys.stderr)
        sys.exit(1)


def load_cases() -> dict[str, dict[str, Any]]:
    with GOLDEN_PATH.open() as file:
        return {case["case_id"]: case for case in json.load(file)}


def payload_for(case: dict[str, Any], live: bool) -> dict[str, Any]:
    payload = {
        "raw_text": case["raw_text"],
        "channel": "chat",
        "customer_ref": case["customer_ref"],
        "today": case.get("today", "2026-03-10"),
        "execute_actions": False,
    }
    if not live:
        payload["support_ticket"] = case["support_ticket"]
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ShopSense API demo cases.")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--timeout", type=float, default=120.0, help="seconds to wait for each response")
    parser.add_argument("--live", action="store_true", help="send raw text only and use the live LLM parser")
    args = parser.parse_args()

    base = args.url.rstrip("/")
    status, body = call(f"{base}/health", timeout=args.timeout)
    print(f"GET /health -> {status}\n{json.dumps(body, indent=2)}\n")

    cases = load_cases()
    for label, case_id in CASE_IDS:
        case = cases[case_id]
        payload = payload_for(case, live=args.live)
        display_payload = {k: v for k, v in payload.items() if k != "support_ticket"}
        mode = "live raw text" if args.live else "deterministic parsed ticket"
        print(f"--- {label} ({mode}) ---")
        print(f"POST /chat {json.dumps(display_payload)}")
        status, body = call(f"{base}/chat", payload, timeout=args.timeout)
        print(f"-> {status}\n{json.dumps(body, indent=2)}\n")


if __name__ == "__main__":
    main()
