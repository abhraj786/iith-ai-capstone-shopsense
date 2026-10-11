"""Qdrant-backed policy index over ShopSense policy documents (M3).

The embedding function is deterministic and local. M4 can replace retrieval quality with
hybrid search/reranking, but M3 gives us a real Qdrant collection and stable policy hits.
"""

import hashlib
import json
import math
import re
from pathlib import Path

from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

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
    return TOKEN.findall(text.lower())


def embed_text(text: str, size: int = VECTOR_SIZE) -> list[float]:
    vector = [0.0] * size
    for token in _tokens(text):
        digest = hashlib.sha1(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % size
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


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


def _point_id(slug: str, chunk_id: int) -> int:
    digest = hashlib.sha1(f"{slug}:{chunk_id}".encode("utf-8")).hexdigest()
    return int(digest[:15], 16)


class PolicyIndex:
    def __init__(self, client: QdrantClient, corpus_root: Path, collection_name: str = COLLECTION_NAME):
        self.client = client
        self.corpus_root = Path(corpus_root)
        self.collection_name = collection_name

    @classmethod
    def local(cls, index_dir: Path | None = None) -> "PolicyIndex":
        settings = get_settings()
        root = PROJECT_ROOT / settings.data_root / settings.domain
        path = index_dir or (PROJECT_ROOT / settings.runtime_root / "qdrant")
        return cls(QdrantClient(path=str(path)), root)

    def load_manifest(self) -> list[dict]:
        return json.loads((self.corpus_root / "corpus" / "index.json").read_text())

    def build(self, recreate: bool = True) -> int:
        if recreate and self.client.collection_exists(self.collection_name):
            self.client.delete_collection(collection_name=self.collection_name)
        if recreate or not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )

        points: list[PointStruct] = []
        for doc in self.load_manifest():
            markdown_path = self.corpus_root / doc["markdown"]
            text = markdown_path.read_text()
            for chunk_id, chunk in enumerate(_chunk_text(text)):
                points.append(PointStruct(
                    id=_point_id(doc["slug"], chunk_id),
                    vector=embed_text(chunk),
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
        return len(points)

    def search(self, query: str, limit: int = 5) -> list[PolicyHit]:
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=embed_text(query),
            limit=limit,
            with_payload=True,
        )
        return [
            PolicyHit(score=float(hit.score), **hit.payload)
            for hit in response.points
        ]
