"""Local and optional LangFuse tracing for ticket-resolution flows."""

from __future__ import annotations

import json
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from capstone.settings import PROJECT_ROOT, get_settings


class TraceRecorder:
    """Record spans locally and forward to LangFuse when configured.

    Local JSONL traces are the source of truth for offline evaluation. LangFuse is
    best-effort so missing credentials or package/API drift never breaks the app.
    """

    def __init__(self, root: Path | None = None):
        settings = get_settings()
        self.root = Path(root or (PROJECT_ROOT / settings.runtime_root / "traces"))
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.root = Path(tempfile.gettempdir()) / "shopsense-traces"
            self.root.mkdir(parents=True, exist_ok=True)
        self._langfuse = _LangFuseSink.from_settings(settings)

    def start_trace(
        self,
        name: str,
        *,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        tags: list[str] | None = None,
    ) -> "TraceRun":
        return TraceRun(
            self,
            name=name,
            metadata=metadata or {},
            session_id=session_id,
            user_id=user_id,
            tags=tags or [],
        )

    def write(self, event: dict[str, Any]) -> None:
        path = self.root / f"{event['trace_id']}.jsonl"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a") as f:
                f.write(json.dumps(event, sort_keys=True, default=str) + "\n")
        except OSError:
            self.root = Path(tempfile.gettempdir()) / "shopsense-traces"
            path = self.root / f"{event['trace_id']}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a") as f:
                f.write(json.dumps(event, sort_keys=True, default=str) + "\n")
        self._langfuse.write(event)


class TraceRun:
    def __init__(
        self,
        recorder: TraceRecorder,
        *,
        name: str,
        metadata: dict[str, Any],
        session_id: str | None,
        user_id: str | None,
        tags: list[str],
    ):
        self.recorder = recorder
        self.trace_id = uuid4().hex
        self.name = name
        self.metadata = metadata
        self.session_id = session_id or self.trace_id
        self.user_id = user_id
        self.tags = tags
        self._span_stack: list[str] = []
        self.started_at = time.time()
        self.recorder.write({
            "event": "trace_start",
            "trace_id": self.trace_id,
            "name": self.name,
            "metadata": self.metadata,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "tags": self.tags,
            "ts": self.started_at,
        })

    @contextmanager
    def span(self, name: str, *, metadata: dict[str, Any] | None = None):
        span = TraceSpan(self, name=name, metadata=metadata or {})
        self._span_stack.append(span.span_id)
        try:
            yield span
        except Exception as exc:
            span.end(error={"type": type(exc).__name__, "message": str(exc)})
            raise
        else:
            span.end()
        finally:
            if self._span_stack and self._span_stack[-1] == span.span_id:
                self._span_stack.pop()
            elif span.span_id in self._span_stack:
                self._span_stack.remove(span.span_id)

    def end(self, *, output: dict[str, Any] | None = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
        ended_at = time.time()
        event = {
            "event": "trace_end",
            "trace_id": self.trace_id,
            "name": self.name,
            "duration_ms": round((ended_at - self.started_at) * 1000, 3),
            "output": output or {},
            "error": error,
            "ts": ended_at,
        }
        self.recorder.write(event)
        return {"trace_id": self.trace_id, "path": str(self.recorder.root / f"{self.trace_id}.jsonl")}


class TraceSpan:
    def __init__(self, trace: TraceRun, *, name: str, metadata: dict[str, Any]):
        self.trace = trace
        self.name = name
        self.metadata = metadata
        self.span_id = uuid4().hex
        self.parent_span_id = trace._span_stack[-1] if trace._span_stack else None
        self.started_at = time.time()
        self.ended = False
        self.trace.recorder.write({
            "event": "span_start",
            "trace_id": self.trace.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "metadata": self.metadata,
            "ts": self.started_at,
        })

    def set_output(self, output: dict[str, Any]) -> None:
        self.output = output

    def end(self, *, output: dict[str, Any] | None = None, error: dict[str, Any] | None = None) -> None:
        if self.ended:
            return
        self.ended = True
        ended_at = time.time()
        self.trace.recorder.write({
            "event": "span_end",
            "trace_id": self.trace.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "duration_ms": round((ended_at - self.started_at) * 1000, 3),
            "output": output or getattr(self, "output", {}),
            "error": error,
            "ts": ended_at,
        })


class _LangFuseSink:
    def __init__(self, client: Any | None = None):
        self.client = client
        self._traces: dict[str, Any] = {}
        self._spans: dict[str, Any] = {}

    @classmethod
    def from_settings(cls, settings) -> "_LangFuseSink":
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            return cls()
        try:
            from langfuse import Langfuse

            kwargs = {
                "public_key": settings.langfuse_public_key,
                "secret_key": settings.langfuse_secret_key,
            }
            if settings.langfuse_host:
                kwargs["host"] = settings.langfuse_host
            return cls(Langfuse(**kwargs))
        except Exception:
            return cls()

    def write(self, event: dict[str, Any]) -> None:
        if self.client is None:
            return
        try:
            if event["event"] == "trace_start":
                self._traces[event["trace_id"]] = self.client.trace(
                    id=event["trace_id"],
                    name=event["name"],
                    metadata=event.get("metadata") or {},
                    session_id=event.get("session_id"),
                    user_id=event.get("user_id"),
                    tags=event.get("tags") or [],
                )
            elif event["event"] == "span_start":
                trace = self._traces.get(event["trace_id"])
                if trace is not None:
                    self._spans[event["span_id"]] = trace.span(
                        name=event["name"],
                        metadata=event.get("metadata") or {},
                    )
            elif event["event"] == "span_end":
                span = self._spans.get(event["span_id"])
                if span is not None:
                    span.end(output=event.get("output"), status_message=json.dumps(event.get("error")) if event.get("error") else None)
            elif event["event"] == "trace_end" and hasattr(self.client, "flush"):
                self.client.flush()
        except Exception:
            return


def read_trace(path: str | Path) -> list[dict[str, Any]]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def summarize_trace(path: str | Path) -> list[dict[str, Any]]:
    events = read_trace(path)
    rows: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("event") != "span_end":
            continue
        role = str(event.get("name"))
        row = rows.setdefault(role, {
            "role": role,
            "calls": 0,
            "total_ms": 0.0,
            "avg_ms": 0.0,
            "errors": 0,
            "fallbacks": 0,
        })
        row["calls"] += 1
        row["total_ms"] += float(event.get("duration_ms") or 0)
        row["errors"] += 1 if event.get("error") else 0
        output = event.get("output") or {}
        reliability = output.get("reliability") if isinstance(output, dict) else None
        if isinstance(reliability, dict) and reliability.get("fallback") not in (None, "none"):
            row["fallbacks"] += 1
    for row in rows.values():
        row["total_ms"] = round(row["total_ms"], 3)
        row["avg_ms"] = round(row["total_ms"] / row["calls"], 3) if row["calls"] else 0.0
    return sorted(rows.values(), key=lambda item: item["total_ms"], reverse=True)


def get_trace_recorder() -> TraceRecorder:
    return TraceRecorder()

