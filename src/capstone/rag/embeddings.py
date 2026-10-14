"""Embedding backends for the policy index (M3/M4).

``gemini`` uses ``gemini-embedding-001`` through LiteLLM (the model taught in the RAG lab) with a
disk cache so re-runs are free and rate-limit friendly. ``hash`` is a deterministic, offline
bag-of-words projection used by unit tests and as a fallback when no key is configured.

Selection: ``CAPSTONE_EMBEDDINGS=gemini|hash``; unset means gemini when a Gemini/Google key exists.
"""

import hashlib
import json
import math
import os
import re
import time
from pathlib import Path

from capstone.settings import PROJECT_ROOT, get_settings

GEMINI_MODEL = "gemini/gemini-embedding-001"
GEMINI_DIM = 768  # gemini-embedding-001 supports Matryoshka truncation; 768 keeps Qdrant small.
HASH_DIM = 64
BATCH = 32
TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


def hash_embed(text: str, size: int = HASH_DIM) -> list[float]:
    vector = [0.0] * size
    for token in _tokens(text):
        digest = hashlib.sha1(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % size
        vector[bucket] += 1.0 if digest[4] % 2 == 0 else -1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def backend_name() -> str:
    choice = (os.getenv("CAPSTONE_EMBEDDINGS") or "").strip().lower()
    if choice in {"gemini", "hash"}:
        return choice
    return "gemini" if (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")) else "hash"


def vector_size() -> int:
    return GEMINI_DIM if backend_name() == "gemini" else HASH_DIM


def collection_suffix() -> str:
    """Keep vectors of different sizes in different collections so one never clobbers another."""
    return "_gemini" if backend_name() == "gemini" else ""


_CACHE: dict[str, list[float]] | None = None


def _cache_path() -> Path:
    settings = get_settings()
    root = settings.runtime_root if settings.runtime_root.is_absolute() else PROJECT_ROOT / settings.runtime_root
    return root / "embedding_cache.json"


def _load_cache() -> dict[str, list[float]]:
    global _CACHE
    if _CACHE is None:
        path = _cache_path()
        _CACHE = json.loads(path.read_text()) if path.exists() else {}
    return _CACHE


def _save_cache() -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_CACHE))


def _key(text: str, task: str) -> str:
    return hashlib.sha1(f"{GEMINI_MODEL}:{GEMINI_DIM}:{task}:{text}".encode("utf-8")).hexdigest()


def _gemini_batch(texts: list[str], task: str) -> list[list[float]]:
    import litellm

    last: Exception | None = None
    for attempt in range(5):
        try:
            response = litellm.embedding(
                model=GEMINI_MODEL, input=texts, dimensions=GEMINI_DIM,
                task_type="RETRIEVAL_DOCUMENT" if task == "document" else "RETRIEVAL_QUERY",
            )
            vectors = [item["embedding"] for item in response.data]
            return [[x / (math.sqrt(sum(y * y for y in v)) or 1.0) for x in v] for v in vectors]
        except Exception as exc:  # rate limit / transient; free tier is ~100 requests per minute
            last = exc
            time.sleep(min(8 * (2 ** attempt), 60))
    raise RuntimeError(f"Gemini embedding failed after retries: {last}")


def embed_texts(texts: list[str], task: str = "document") -> list[list[float]]:
    if backend_name() == "hash":
        return [hash_embed(t) for t in texts]
    cache = _load_cache()
    missing = [t for t in dict.fromkeys(texts) if _key(t, task) not in cache]
    for start in range(0, len(missing), BATCH):
        batch = missing[start:start + BATCH]
        for text, vector in zip(batch, _gemini_batch(batch, task)):
            cache[_key(text, task)] = vector
        _save_cache()
    return [cache[_key(t, task)] for t in texts]


def embed_query(text: str) -> list[float]:
    return embed_texts([text], task="query")[0]
