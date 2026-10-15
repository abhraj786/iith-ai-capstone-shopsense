"""M7: how much does tracing itself cost? Run the same ticket traced and untraced and compare.

Offline (fake LLM, in-process tools), so the numbers isolate tracing from model latency.
Report the UNTRACED figure as the team's own time; the delta is what visibility costs.
"""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from qdrant_client import QdrantClient

from capstone.agents.policy_agent import PolicyAgent
from capstone.llm.client import LLMClient
from capstone.memory.store import CustomerMemoryStore
from capstone.observability.tracing import TraceRecorder, _LangFuseSink
from capstone.rag.hybrid import HybridPolicyRetriever
from capstone.rag.policy_index import PolicyIndex
from capstone.settings import Settings, get_settings
from capstone.team.multi_agent import MultiAgentTeam
from capstone.tools.repository import Repository

TICKET = {
    "issue_type": "track_order", "order_ref": "KW-O-000950", "sentiment": "calm", "urgency": "normal",
    "claimed_amount_inr": None, "contact_number": 1, "escalation_signals": [],
    "prompt_injection_suspected": False, "missing_fields": [], "summary": "Customer asks where the order is.",
}


class NullRecorder(TraceRecorder):
    """Same spans, nothing written: the untraced baseline."""

    def write(self, event):  # noqa: D401
        return None


class LocalRecorder(TraceRecorder):
    """JSONL only: Langfuse forwarding switched off."""

    def __init__(self, root):
        super().__init__(root)
        self._langfuse = _LangFuseSink()


def _completion(**kwargs):
    body = {"route": "fast_track", "reason": "plain tracking"} \
        if kwargs["response_format"].__name__ == "SupervisorDecision" else TICKET
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(body)))])


def _time_runs(recorder_cls, root: Path, index: PolicyIndex, n: int) -> list[float]:
    team = MultiAgentTeam(
        client=LLMClient(Settings(llm_max_retries=0), completion=_completion),
        repo=Repository(get_settings().seed_dir, root / "state"),
        memory_store=CustomerMemoryStore(root / "memory"),
        policy_index=index, policy_agent=PolicyAgent(HybridPolicyRetriever(index)),
        tool_gateway=None, use_mcp_tools=False, tracer=recorder_cls(root / "traces"),
    )
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        team.resolve(raw_text="Where is KW-O-000950?", channel="chat", customer_ref="KW-C-00285", today="2026-03-10")
        times.append((time.perf_counter() - t0) * 1000)
    return times


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=20)
    n = parser.parse_args().n
    index = PolicyIndex(QdrantClient(":memory:"), get_settings().data_root / get_settings().domain)
    index.build()
    with tempfile.TemporaryDirectory() as tmp:
        untraced = _time_runs(NullRecorder, Path(tmp) / "a", index, n)
        local = _time_runs(LocalRecorder, Path(tmp) / "b", index, n)
        full = _time_runs(TraceRecorder, Path(tmp) / "c", index, n)
    u, l, f = (statistics.median(x) for x in (untraced, local, full))
    print(f"untraced: {u:.2f} ms | local JSONL trace: {l:.2f} ms ({l - u:+.2f}) | "
          f"JSONL + Langfuse: {f:.2f} ms ({f - u:+.2f})  [median of {n} runs each]")
    print("Report the untraced number as real latency; the deltas are what visibility costs.")


if __name__ == "__main__":
    main()
