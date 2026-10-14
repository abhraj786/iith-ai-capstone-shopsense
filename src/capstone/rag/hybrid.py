"""Hybrid policy retrieval (M4): dense + BM25 fused with RRF, then cross-encoder reranking.

The cross-encoder (ONNX via fastembed) is optional; when it cannot load the fused order is kept.
"""

import os
from dataclasses import dataclass
from functools import lru_cache

from rank_bm25 import BM25Okapi

from capstone.rag import embeddings
from capstone.rag.policy_index import PolicyHit, PolicyIndex, _chunk_text, _tokens

BM25_BOOST = 0.02  # semantic dense vectors already carry meaning; BM25 only breaks near-ties
BM25_BOOST_LEXICAL = 0.5  # offline hash vectors are lexical, so BM25 is a peer signal there
RERANK_WEIGHT = 0.05

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "can", "for", "from", "i", "in",
    "is", "it", "of", "on", "or", "the", "to", "under", "what", "when", "with",
}


@dataclass(frozen=True)
class CorpusChunk:
    document_slug: str
    title: str
    section: str
    chunk_id: int
    text: str


def _query_terms(query: str) -> set[str]:
    return {t for t in _tokens(query) if t not in STOPWORDS and len(t) > 1}


class HybridPolicyRetriever:
    def __init__(self, index: PolicyIndex, rerank: bool | None = None):
        self.index = index
        self._bm25: BM25Okapi | None = None
        self._chunks: list[CorpusChunk] | None = None
        self.rerank = (os.getenv("CAPSTONE_RERANK", "on").lower() != "off") if rerank is None else rerank

    def ensure_index(self) -> None:
        if not self.index.client.collection_exists(self.index.collection_name):
            self.index.build(recreate=False)

    def corpus_chunks(self) -> list[CorpusChunk]:
        if self._chunks is not None:
            return self._chunks
        chunks: list[CorpusChunk] = []
        for doc in self.index.load_manifest():
            text = (self.index.corpus_root / doc["markdown"]).read_text()
            for chunk_id, chunk in enumerate(_chunk_text(text)):
                chunks.append(CorpusChunk(
                    document_slug=doc["slug"],
                    title=doc["title"],
                    section=doc["section"],
                    chunk_id=chunk_id,
                    text=chunk,
                ))
        self._chunks = chunks
        return chunks

    def _bm25_index(self) -> BM25Okapi:
        if self._bm25 is None:
            self._bm25 = BM25Okapi([
                _tokens(" ".join([c.document_slug.replace("-", " "), c.title, c.text]))
                for c in self.corpus_chunks()
            ])
        return self._bm25

    def keyword_search(self, query: str, limit: int = 12, exclude_slugs: list[str] | None = None) -> list[PolicyHit]:
        """BM25 over chunk text (plus slug/title), a deterministic exact-token complement to dense."""
        terms = [t for t in _tokens(query) if t not in STOPWORDS and len(t) > 1]
        if not terms:
            return []
        chunks = self.corpus_chunks()
        scores = self._bm25_index().get_scores(terms)
        skip = set(exclude_slugs or [])
        ranked = [i for i in sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
                  if chunks[i].document_slug not in skip][:limit]
        return [
            PolicyHit(score=float(scores[i]), document_slug=chunks[i].document_slug, title=chunks[i].title,
                      section=chunks[i].section, chunk_id=chunks[i].chunk_id, text=chunks[i].text)
            for i in ranked if scores[i] > 0
        ]

    def fused_search(self, query: str, limit: int = 12, pool: int = 20,
                     category: str | None = None) -> list[PolicyHit]:
        """Dense similarity plus a small normalised BM25 boost.

        Rank-based RRF was tried first and lost to dense-only on the golden set: BM25 cannot bridge
        vocabulary gaps ("laptop" vs the Electronics addendum), and RRF flattens score gaps so even a
        small BM25 weight reshuffles the top results. A score-level boost keeps dense dominant while
        still rewarding exact policy terms (see evaluation/reports/m4_retrieval_eval.json).
        """
        skip = self.index.excluded_for(category)
        dense = {(h.document_slug, h.chunk_id): h for h in self.index.search(query, limit=pool, exclude_slugs=skip)}
        sparse = {(h.document_slug, h.chunk_id): h for h in self.keyword_search(query, limit=pool, exclude_slugs=skip)}
        top = max((h.score for h in sparse.values()), default=1.0) or 1.0
        boost = BM25_BOOST_LEXICAL if embeddings.backend_name() == "hash" else BM25_BOOST
        floor = min((h.score for h in dense.values()), default=0.0)
        fused: dict[tuple[str, int], float] = {}
        for key in dense.keys() | sparse.keys():
            base = dense[key].score if key in dense else floor
            fused[key] = base + boost * (sparse[key].score / top if key in sparse else 0.0)
        order = sorted(fused, key=fused.get, reverse=True)[:limit]
        return [(dense.get(k) or sparse[k]).model_copy(update={"score": fused[k]}) for k in order]

    def retrieve(self, query: str, limit: int = 5, category: str | None = None) -> list[PolicyHit]:
        self.ensure_index()
        candidates = self.fused_search(query, limit=max(limit * 3, 12), category=category)
        encoder = _cross_encoder() if self.rerank else None
        if encoder is None or not candidates:
            return candidates[:limit]
        raw = [float(x) for x in encoder.rerank(query, [hit.text for hit in candidates])]
        low, high = min(raw), max(raw)
        blended = [
            hit.model_copy(update={"score": hit.score + RERANK_WEIGHT * ((x - low) / ((high - low) or 1.0))})
            for hit, x in zip(candidates, raw)
        ]
        return sorted(blended, key=lambda hit: hit.score, reverse=True)[:limit]


@lru_cache(maxsize=1)
def _cross_encoder():
    """Cross-encoder reranker (fastembed ONNX). Returns None when unavailable so retrieval degrades."""
    try:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        return TextCrossEncoder(model_name="Xenova/ms-marco-MiniLM-L-6-v2")
    except Exception:
        return None
