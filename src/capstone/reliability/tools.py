"""Retries, fallback signals, and circuit breaking for ShopSense tool calls."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from capstone.settings import get_settings

TRANSIENT_ERRORS = {
    "timeout",
    "connection_error",
    "tool_unavailable",
    "mcp_tool_error",
    "rate_limited",
    "circuit_open",
}
FALLBACK_ERRORS = TRANSIENT_ERRORS | {"malformed_response"}


@dataclass
class RetryPolicy:
    attempts: int = 2
    backoff_s: float = 0.01
    max_backoff_s: float = 0.2


@dataclass
class CircuitBreaker:
    failure_threshold: int = 2
    cooldown_s: float = 30.0
    failures: dict[str, int] = field(default_factory=dict)
    opened_at: dict[str, float] = field(default_factory=dict)

    def allow(self, tool_name: str) -> bool:
        opened = self.opened_at.get(tool_name)
        if opened is None:
            return True
        if time.time() - opened >= self.cooldown_s:
            self.failures[tool_name] = 0
            self.opened_at.pop(tool_name, None)
            return True
        return False

    def record_success(self, tool_name: str) -> None:
        self.failures[tool_name] = 0
        self.opened_at.pop(tool_name, None)

    def record_failure(self, tool_name: str) -> None:
        count = self.failures.get(tool_name, 0) + 1
        self.failures[tool_name] = count
        if count >= self.failure_threshold:
            self.opened_at[tool_name] = time.time()

    def state(self, tool_name: str) -> str:
        return "open" if not self.allow(tool_name) else "closed"


class ReliableToolGateway:
    """Wrap a tool gateway with retry and circuit-breaker behavior."""

    def __init__(
        self,
        gateway: Any,
        *,
        retry_policy: RetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ):
        settings = get_settings()
        self.gateway = gateway
        self.retry_policy = retry_policy or RetryPolicy(attempts=settings.tool_retry_attempts)
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=settings.tool_circuit_failure_threshold,
            cooldown_s=settings.tool_circuit_cooldown_s,
        )

    def __getattr__(self, name: str) -> Callable:
        target = getattr(self.gateway, name)

        def call(*args, **kwargs):
            return self._call(name, target, *args, **kwargs)

        return call

    def _call(self, tool_name: str, target: Callable, *args, **kwargs) -> dict[str, Any]:
        if not self.circuit_breaker.allow(tool_name):
            return {
                "ok": False,
                "transport": getattr(self.gateway, "transport", None) or _transport_from_result({}),
                "error": {"error": "circuit_open", "message": f"Circuit open for {tool_name}"},
                "reliability": {"attempts": 0, "circuit": "open", "fallback": "human_queue"},
            }

        last: dict[str, Any] | None = None
        for attempt in range(1, self.retry_policy.attempts + 1):
            try:
                result = target(*args, **kwargs)
            except Exception as exc:
                result = {
                    "ok": False,
                    "error": {"error": "tool_unavailable", "message": f"{type(exc).__name__}: {exc}"},
                }
            last = dict(result)
            if last.get("ok", True) or not _is_transient(last):
                break
            if attempt < self.retry_policy.attempts:
                delay = min(self.retry_policy.backoff_s * (2 ** (attempt - 1)), self.retry_policy.max_backoff_s)
                time.sleep(delay)

        assert last is not None
        reliability = {"attempts": attempt, "circuit": "closed"}
        if last.get("ok", True):
            self.circuit_breaker.record_success(tool_name)
        else:
            self.circuit_breaker.record_failure(tool_name)
            reliability["fallback"] = "human_queue" if _uses_fallback(last) else "none"
        last["reliability"] = {**last.get("reliability", {}), **reliability}
        return last


def _is_transient(result: dict[str, Any]) -> bool:
    error = result.get("error") or {}
    return error.get("error") in TRANSIENT_ERRORS


def _uses_fallback(result: dict[str, Any]) -> bool:
    error = result.get("error") or {}
    return error.get("error") in FALLBACK_ERRORS


def _transport_from_result(result: dict[str, Any]) -> str:
    return str(result.get("transport") or "python")

