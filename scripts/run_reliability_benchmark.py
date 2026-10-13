"""Seeded M7 reliability benchmark for transient tool failures."""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass

from capstone.reliability.tools import CircuitBreaker, ReliableToolGateway, RetryPolicy


@dataclass(frozen=True)
class FaultConfig:
    seed: int = 42
    fail_rate: float = 0.2
    timeout_rate: float = 0.1
    malformed_rate: float = 0.1


class FlakyTrackingGateway:
    def __init__(self, config: FaultConfig):
        self.rng = random.Random(config.seed)
        self.config = config
        self.calls = 0

    def track_shipment(self, customer_ref: str, order_ref: str) -> dict:
        self.calls += 1
        roll = self.rng.random()
        if roll < self.config.fail_rate:
            return {"ok": False, "error": {"error": "connection_error", "message": "seeded connection failure"}}
        if roll < self.config.fail_rate + self.config.timeout_rate:
            return {"ok": False, "error": {"error": "timeout", "message": "seeded timeout"}}
        if roll < self.config.fail_rate + self.config.timeout_rate + self.config.malformed_rate:
            return {"ok": False, "error": {"error": "malformed_response", "message": "missing shipment state"}}
        return {"ok": True, "result": {"order_ref": order_ref, "state": "in_transit"}}


def run_baseline(config: FaultConfig, n: int) -> dict:
    gateway = FlakyTrackingGateway(config)
    ok = transient = malformed = 0
    for _ in range(n):
        result = gateway.track_shipment("KW-C-00285", "KW-O-000950")
        if result.get("ok"):
            ok += 1
        elif result["error"]["error"] == "malformed_response":
            malformed += 1
        else:
            transient += 1
    return {"ok": ok, "transient": transient, "malformed": malformed, "success_rate": ok / n}


def run_hardened(config: FaultConfig, n: int) -> dict:
    gateway = ReliableToolGateway(
        FlakyTrackingGateway(config),
        retry_policy=RetryPolicy(attempts=4, backoff_s=0, max_backoff_s=0),
        circuit_breaker=CircuitBreaker(failure_threshold=n + 1),
    )
    ok = fallback = malformed = 0
    for _ in range(n):
        result = gateway.track_shipment("KW-C-00285", "KW-O-000950")
        if result.get("ok"):
            ok += 1
        elif result.get("reliability", {}).get("fallback") == "human_queue":
            fallback += 1
        else:
            malformed += 1
    return {
        "ok": ok,
        "fallback": fallback,
        "malformed": malformed,
        "handled_rate": (ok + fallback + malformed) / n,
        "clean_success_rate": ok / n,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    config = FaultConfig(seed=args.seed)
    baseline = run_baseline(config, args.n)
    hardened = run_hardened(config, args.n)

    print("stage,ok,transient_or_fallback,malformed,success_or_handled_rate")
    print(
        "baseline,"
        f"{baseline['ok']},{baseline['transient']},{baseline['malformed']},{baseline['success_rate']:.3f}"
    )
    print(
        "hardened,"
        f"{hardened['ok']},{hardened['fallback']},{hardened['malformed']},{hardened['handled_rate']:.3f}"
    )


if __name__ == "__main__":
    main()
