"""Hybrid policy retrieval and reranking (M4)."""

from dataclasses import dataclass

from capstone.rag.policy_index import PolicyHit, PolicyIndex, _chunk_text, _tokens

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
    def __init__(self, index: PolicyIndex):
        self.index = index

    def ensure_index(self) -> None:
        if not self.index.client.collection_exists(self.index.collection_name):
            self.index.build(recreate=False)

    def corpus_chunks(self) -> list[CorpusChunk]:
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
        return chunks

    def keyword_search(self, query: str, limit: int = 12) -> list[PolicyHit]:
        terms = _query_terms(query)
        scored: list[PolicyHit] = []
        for chunk in self.corpus_chunks():
            haystack = " ".join([chunk.document_slug, chunk.title, chunk.text]).lower()
            chunk_terms = set(_tokens(haystack))
            overlap = terms & chunk_terms
            if not overlap:
                continue
            score = len(overlap) / max(len(terms), 1)
            for term in terms:
                if term in chunk.document_slug.lower():
                    score += 0.25
                if term in chunk.title.lower():
                    score += 0.20
            scored.append(PolicyHit(
                score=score,
                document_slug=chunk.document_slug,
                title=chunk.title,
                section=chunk.section,
                chunk_id=chunk.chunk_id,
                text=chunk.text,
            ))
        return sorted(scored, key=lambda hit: hit.score, reverse=True)[:limit]

    def retrieve(self, query: str, limit: int = 5) -> list[PolicyHit]:
        self.ensure_index()
        vector_hits = self.index.search(query, limit=max(limit * 3, 12))
        keyword_hits = self.keyword_search(query, limit=max(limit * 3, 12))
        merged: dict[tuple[str, int], PolicyHit] = {}
        scores: dict[tuple[str, int], float] = {}

        for rank, hit in enumerate(vector_hits):
            key = (hit.document_slug, hit.chunk_id)
            merged[key] = hit
            scores[key] = scores.get(key, 0.0) + hit.score + 0.05 * (len(vector_hits) - rank)

        for rank, hit in enumerate(keyword_hits):
            key = (hit.document_slug, hit.chunk_id)
            merged.setdefault(key, hit)
            scores[key] = scores.get(key, 0.0) + (1.8 * hit.score) + 0.05 * (len(keyword_hits) - rank)

        reranked = [
            hit.model_copy(update={"score": scores[(hit.document_slug, hit.chunk_id)]})
            for hit in merged.values()
        ]
        return sorted(reranked, key=lambda hit: hit.score, reverse=True)[:limit]
