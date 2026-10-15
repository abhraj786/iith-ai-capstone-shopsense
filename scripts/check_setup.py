"""Preflight for evaluators: confirms each external service in .env really works. Prints no secrets.

Run:  python -m scripts.check_setup
"""

from __future__ import annotations

import os
import sys

from capstone.settings import get_settings


def _llm() -> str:
    from capstone.llm.client import LLMClient
    from pydantic import BaseModel

    class Ping(BaseModel):
        ok: bool

    LLMClient().structured("Reply with ok=true.", "ping", Ping)
    return f"model {get_settings().llm_model} answered"


def _qdrant() -> str:
    from qdrant_client import QdrantClient

    url = os.getenv("QDRANT_URL") or os.getenv("CAPSTONE_QDRANT_URL")
    key = os.getenv("QDRANT_API_KEY") or os.getenv("CAPSTONE_QDRANT_API_KEY")
    if not (url and key):
        raise RuntimeError("QDRANT_URL and QDRANT_API_KEY are not set")
    n = len(QdrantClient(url=url, api_key=key).get_collections().collections)
    return f"cluster reachable, {n} collection(s)"


def _langfuse() -> str:
    from langfuse import Langfuse

    s = get_settings()
    pub = s.langfuse_public_key or os.getenv("LANGFUSE_PUBLIC_KEY")
    sec = s.langfuse_secret_key or os.getenv("LANGFUSE_SECRET_KEY")
    host = s.langfuse_host or os.getenv("LANGFUSE_HOST") or "https://cloud.langfuse.com"
    if not (pub and sec):
        raise RuntimeError("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are not set")
    if not Langfuse(public_key=pub, secret_key=sec, host=host).auth_check():
        raise RuntimeError("Langfuse rejected the keys")
    return f"authenticated against {host}"


def main() -> int:
    failed = 0
    for name, check in [("LLM provider", _llm), ("Qdrant Cloud", _qdrant), ("Langfuse", _langfuse)]:
        try:
            print(f"OK    {name}: {check()}")
        except Exception as exc:  # report the reason, never the key
            failed += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {str(exc)[:160]}")
    print("\nAll external services ready." if not failed else f"\n{failed} service(s) need attention; fix .env and rerun.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
