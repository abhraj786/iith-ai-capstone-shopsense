"""Local and optional LangFuse tracing for ticket-resolution flows."""

from __future__ import annotations

import json
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType
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
        self.root.mkdir(parents=True, exist_ok=True)
        self._langfuse = _LangFuseSink.from_settings(settings)

    def start_trace(self, name: str, *, metadata: dict[str, Any] | None = None) -> "TraceRun":
        return TraceRun(self, name=name, metadata=metadata or {})

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
    def __init__(self, recorder: TraceRecorder, *, name: str, metadata: dict[str, Any]):
        self.recorder = recorder
        self.trace_id = uuid4().hex
        self.name = name
        self.metadata = metadata
        self.started_at = time.time()
        self.recorder.write({
            "event": "trace_start",
            "trace_id": self.trace_id,
            "name": self.name,
            "metadata": self.metadata,
            "ts": self.started_at,
        })

    @contextmanager
    def span(self, name: str, *, metadata: dict[str, Any] | None = None):
        span = TraceSpan(self, name=name, metadata=metadata or {})
        try:
            yield span
        except Exception as exc:
            span.end(error={"type": type(exc).__name__, "message": str(exc)})
            raise
        else:
            span.end()

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
        self.started_at = time.time()
        self.ended = False
        self.trace.recorder.write({
            "event": "span_start",
            "trace_id": self.trace.trace_id,
            "span_id": self.span_id,
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


def get_trace_recorder() -> TraceRecorder:
    return TraceRecorder()

