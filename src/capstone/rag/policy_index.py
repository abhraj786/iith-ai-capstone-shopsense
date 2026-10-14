"""Qdrant-backed policy index over ShopSense policy documents (M3).

The embedding function is deterministic and local. M4 can replace retrieval quality with
hybrid search/reranking, but M3 gives us a real Qdrant collection and stable policy hits.
"""

import hashlib
import json
import os
import re
import warnings
from pathlib import Path

from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, MatchAny, PayloadSchemaType, PointStruct, VectorParams,
)

from capstone.rag import embeddings
from capstone.settings import PROJECT_ROOT, get_settings

COLLECTION_NAME = "shopsense_policy_m3"
VECTOR_SIZE = 64
TOKEN = re.compile(r"[a-z0-9]+")


class PolicyHit(BaseModel):
    score: float
    document_slug: str
    title: str
    section: str
    chunk_id: int
    text: str


def _tokens(text: str) -> list[str]:
    return embeddings._tokens(text)


def embed_text(text: str, size: int = VECTOR_SIZE) -> list[float]:
    """Deterministic offline embedding kept for tests; the index itself uses ``embeddings``."""
    return embeddings.hash_embed(text, size)


def _chunk_text(text: str, max_words: int = 180, overlap: int = 35) -> list[str]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    chunks: list[str] = []
    current: list[str] = []
    for block in blocks:
        words = block.split()
        if current and len(current) + len(words) > max_words:
            chunks.append(" ".join(current))
            current = current[-overlap:]
        current.extend(words)
    if current:
        chunks.append(" ".join(current))
    return chunks


def category_slug(category: str) -> str:
    """'Home & Kitchen' -> 'category-home-kitchen'."""
    return "category-" + "-".join(re.findall(r"[a-z0-9]+", category.lower()))


def _point_id(slug: str, chunk_id: int) -> int:
    digest = hashlib.sha1(f"{slug}:{chunk_id}".encode("utf-8")).hexdigest()
    return int(digest[:15], 16)


class PolicyIndex:
    def __init__(
        self,
        client: QdrantClient,
        corpus_root: Path,
        collection_name: str = COLLECTION_NAME,
        storage_label: str = "custom",
    ):
        self.client = client
        self.corpus_root = Path(corpus_root)
        suffix = embeddings.collection_suffix()
        self.collection_name = collection_name if collection_name.endswith(suffix) else collection_name + suffix
        self.storage_label = storage_label

    @classmethod
    def local(cls, index_dir: Path | None = None) -> "PolicyIndex":
        settings = get_settings()
        root = PROJECT_ROOT / settings.data_root / settings.domain
        path = index_dir or (PROJECT_ROOT / settings.runtime_root / "qdrant")
        return cls(QdrantClient(path=str(path)), root, storage_label="local")

    @classmethod
    def from_settings(cls, index_dir: Path | None = None) -> "PolicyIndex":
        """Use Qdrant Cloud when configured; otherwise use the local persistent store.

        The course notebooks demonstrate Qdrant Cloud. Keeping a local fallback lets an
        evaluator run the project without private cloud credentials while preserving the
        same Qdrant collection boundary.
        """
        settings = get_settings()
        root = PROJECT_ROOT / settings.data_root / settings.domain
        qdrant_url = os.getenv("QDRANT_URL") or os.getenv("CAPSTONE_QDRANT_URL")
        qdrant_key = os.getenv("QDRANT_API_KEY") or os.getenv("CAPSTONE_QDRANT_API_KEY")
        collection = os.getenv("QDRANT_COLLECTION") or os.getenv("CAPSTONE_QDRANT_COLLECTION") or COLLECTION_NAME
        if qdrant_url and qdrant_key:
            try:
                client = QdrantClient(url=qdrant_url, api_key=qdrant_key)
                client.get_collections()
                return cls(client, root, collection, "cloud")
            except Exception as exc:
                warnings.warn(
                    f"Qdrant Cloud is configured but unavailable; falling back to local Qdrant: {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )
        return cls.local(index_dir=index_dir)

    def load_manifest(self) -> list[dict]:
        return json.loads((self.corpus_root / "corpus" / "index.json").read_text())

    def build(self, recreate: bool = True) -> int:
        if recreate and self.client.collection_exists(self.collection_name):
            self.client.delete_collection(collection_name=self.collection_name)
        if recreate or not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=embeddings.vector_size(), distance=Distance.COSINE),
            )

        records: list[tuple[dict, int, str]] = []
        for doc in self.load_manifest():
            text = (self.corpus_root / doc["markdown"]).read_text()
            records.extend((doc, chunk_id, chunk) for chunk_id, chunk in enumerate(_chunk_text(text)))
        vectors = embeddings.embed_texts([chunk for _, _, chunk in records], task="document")
        points: list[PointStruct] = []
        for (doc, chunk_id, chunk), vector in zip(records, vectors):
            points.append(PointStruct(
                id=_point_id(doc["slug"], chunk_id),
                vector=vector,
                payload={
                    "document_slug": doc["slug"],
                    "title": doc["title"],
                    "section": doc["section"],
                    "chunk_id": chunk_id,
                    "text": chunk,
                },
            ))
        if points:
            self.client.upsert(collection_name=self.collection_name, points=points)
        self.ensure_payload_index()
        return len(points)

    def ensure_payload_index(self) -> None:
        """Qdrant Cloud refuses to filter on a field without a payload index; creating it is idempotent."""
        if getattr(self, "_payload_indexed", False):
            return
        self.client.create_payload_index(
            collection_name=self.collection_name, field_name="document_slug",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        self._payload_indexed = True

    def category_slugs(self) -> list[str]:
        return [doc["slug"] for doc in self.load_manifest() if doc["slug"].startswith("category-")]

    def excluded_for(self, category: str | None) -> list[str]:
        """Category addenda that must not be consulted for an order in ``category``."""
        if not category:
            return []
        keep = category_slug(category)
        return [slug for slug in self.category_slugs() if slug != keep]

    def search(self, query: str, limit: int = 5, exclude_slugs: list[str] | None = None) -> list[PolicyHit]:
        if exclude_slugs:
            self.ensure_payload_index()
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=embeddings.embed_query(query),
            limit=limit,
            with_payload=True,
            query_filter=Filter(must_not=[FieldCondition(key="document_slug", match=MatchAny(any=exclude_slugs))])
            if exclude_slugs else None,
        )
        return [
            PolicyHit(score=float(hit.score), **hit.payload)
            for hit in response.points
        ]
