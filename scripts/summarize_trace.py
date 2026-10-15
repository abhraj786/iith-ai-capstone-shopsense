"""Print a compact latency/fallback dashboard for a ShopSense trace JSONL file."""

from __future__ import annotations

import argparse
from pathlib import Path

from capstone.observability.tracing import summarize_trace


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace_path", type=Path, help="Path returned in TeamResult.trace['path']")
    args = parser.parse_args()

    rows = summarize_trace(args.trace_path)
    if not rows:
        print("No span_end events found.")
        return

    print("role,calls,total_ms,avg_ms,errors,fallbacks,input_tokens,output_tokens,cost_usd")
    for row in rows:
        print(",".join(str(row[key]) for key in ["role", "calls", "total_ms", "avg_ms", "errors", "fallbacks", "input_tokens", "output_tokens", "cost_usd"]))


if __name__ == "__main__":
    main()
