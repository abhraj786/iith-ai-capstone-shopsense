"""Local and optional LangFuse tracing for ticket-resolution flows."""

from __future__ import annotations

import json
import os
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

    def __init__(self, root: Path | None = None, *, require_langfuse: bool = False):
        settings = get_settings()
        self.root = Path(root or (PROJECT_ROOT / settings.runtime_root / "traces"))
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.root = Path(tempfile.gettempdir()) / "shopsense-traces"
            self.root.mkdir(parents=True, exist_ok=True)
        self._langfuse = _LangFuseSink.from_settings(settings, required=require_langfuse)

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

    def score(self, trace_id: str, name: str, value: float) -> None:
        self._langfuse.score(trace_id, name, value)

    def langfuse_url(self, trace_id: str) -> str | None:
        return self._langfuse.url_for_trace(trace_id)


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
        result = {"trace_id": self.trace_id, "path": str(self.recorder.root / f"{self.trace_id}.jsonl")}
        langfuse_url = self.recorder.langfuse_url(self.trace_id)
        if langfuse_url:
            result["langfuse_url"] = langfuse_url
        return result


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
    def __init__(self, client: Any | None = None, *, required: bool = False):
        self.client = client
        self.required = required
        self._traces: dict[str, Any] = {}
        self._spans: dict[str, Any] = {}
        self._trace_ids: dict[str, str] = {}

    @classmethod
    def from_settings(cls, settings, *, required: bool = False) -> "_LangFuseSink":
        public_key = settings.langfuse_public_key or os.getenv("LANGFUSE_PUBLIC_KEY")
        secret_key = settings.langfuse_secret_key or os.getenv("LANGFUSE_SECRET_KEY")
        host = settings.langfuse_host or os.getenv("LANGFUSE_HOST")
        if not public_key or not secret_key:
            if required:
                raise RuntimeError(
                    "Strict real mode requires Langfuse keys. Set CAPSTONE_LANGFUSE_PUBLIC_KEY "
                    "and CAPSTONE_LANGFUSE_SECRET_KEY, or LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY."
                )
            return cls()
        try:
            from langfuse import Langfuse

            kwargs = {
                "public_key": public_key,
                "secret_key": secret_key,
            }
            if host:
                kwargs["host"] = host
            return cls(Langfuse(**kwargs), required=required)
        except Exception as exc:
            if required:
                raise RuntimeError(f"Could not initialize Langfuse client: {type(exc).__name__}: {exc}") from exc
            return cls()

    def write(self, event: dict[str, Any]) -> None:
        if self.client is None:
            return
        try:
            if event["event"] == "trace_start":
                trace_id = self._langfuse_trace_id(event["trace_id"])
                root = self.client.start_observation(
                    trace_context={"trace_id": trace_id},
                    name=event["name"],
                    as_type="chain",
                    input=event.get("metadata") or {},
                    metadata=event.get("metadata") or {},
                )
                if hasattr(root, "update_trace"):
                    root.update_trace(
                        session_id=event.get("session_id"),
                        user_id=event.get("user_id"),
                        tags=event.get("tags") or [],
                    )
                self._traces[event["trace_id"]] = root
            elif event["event"] == "span_start":
                trace_id = self._langfuse_trace_id(event["trace_id"])
                parent = self._spans.get(event.get("parent_span_id")) or self._traces.get(event["trace_id"])
                parent_span_id = getattr(parent, "id", None)
                span = self.client.start_observation(
                    trace_context={"trace_id": trace_id, "parent_span_id": parent_span_id}
                    if parent_span_id
                    else {"trace_id": trace_id},
                    name=event["name"],
                    as_type=self._observation_type(event["name"]),
                    metadata=event.get("metadata") or {},
                )
                self._spans[event["span_id"]] = span
            elif event["event"] == "span_end":
                span = self._spans.get(event["span_id"])
                if span is not None:
                    span.update(
                        output=event.get("output"),
                        level="ERROR" if event.get("error") else "DEFAULT",
                        status_message=json.dumps(event.get("error")) if event.get("error") else None,
                    )
                    span.end()
            elif event["event"] == "trace_end":
                trace = self._traces.get(event["trace_id"])
                if trace is not None:
                    trace.update(
                        output=event.get("output"),
                        level="ERROR" if event.get("error") else "DEFAULT",
                        status_message=json.dumps(event.get("error")) if event.get("error") else None,
                    )
                    trace.end()
                if hasattr(self.client, "flush"):
                    self.client.flush()
        except Exception as exc:
            if self.required:
                raise RuntimeError(f"Could not forward trace event to Langfuse: {type(exc).__name__}: {exc}") from exc
            return

    def score(self, local_trace_id: str, name: str, value: float) -> None:
        """Attach a numeric score to a trace (best-effort, like every other LangFuse write)."""
        trace_id = self._trace_ids.get(local_trace_id)
        if self.client is None or trace_id is None:
            return
        try:
            self.client.create_score(trace_id=trace_id, name=name, value=float(value))
            if hasattr(self.client, "flush"):
                self.client.flush()
        except Exception as exc:
            if self.required:
                raise RuntimeError(f"Could not send score to Langfuse: {type(exc).__name__}: {exc}") from exc

    def _langfuse_trace_id(self, local_trace_id: str) -> str:
        trace_id = self._trace_ids.get(local_trace_id)
        if trace_id is None:
            trace_id = self.client.create_trace_id(seed=local_trace_id)
            self._trace_ids[local_trace_id] = trace_id
        return trace_id

    def url_for_trace(self, local_trace_id: str) -> str | None:
        if self.client is None or not hasattr(self.client, "get_trace_url"):
            return None
        trace_id = self._trace_ids.get(local_trace_id)
        if trace_id is None:
            return None
        try:
            return self.client.get_trace_url(trace_id=trace_id)
        except Exception:
            return None

    @staticmethod
    def _observation_type(name: str) -> str:
        lowered = name.lower()
        if lowered.startswith("tool.") or "tool" in lowered:
            return "tool"
        if "agent" in lowered:
            return "agent"
        if "retrieval" in lowered or "rag" in lowered:
            return "retriever"
        if "guardrail" in lowered:
            return "guardrail"
        return "span"


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

