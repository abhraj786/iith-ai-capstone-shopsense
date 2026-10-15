"""Grounded policy-answer agent (M4).

This agent is intentionally evidence-first: it retrieves policy chunks, extracts relevant
sentences, and refuses unsupported answers instead of inventing windows, amounts, or routes.
"""

import re

from capstone.rag.hybrid import HybridPolicyRetriever
from capstone.rag.policy_index import PolicyHit, PolicyIndex, _tokens, category_slug
from capstone.schemas.policy import PolicyAnswer, PolicyCitation

NUMBER = re.compile(r"\b\d[\d,]*(?:\.\d+)?\b")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|(?=\* \*\*)|(?=### )")
ANSWER_PREFIX = "Based on the retrieved policy evidence:"


def _query_terms(question: str) -> set[str]:
    stop = {"a", "an", "and", "are", "as", "at", "be", "can", "for", "from", "i",
            "in", "is", "it", "of", "on", "or", "the", "to", "under", "what",
            "when", "with", "my"}
    return {t for t in _tokens(question) if t not in stop and len(t) > 1}


def _sentences(text: str) -> list[str]:
    parts = [p.strip(" -*#") for p in SENTENCE_SPLIT.split(text) if p.strip(" -*#")]
    # Skip document front matter (title / reference block) and overlong run-ons.
    return [p for p in parts if len(p.split()) >= 5 and "Document Reference" not in p and len(p) <= 400]


def _stem(term: str) -> str:
    return term[:5]


DURATION_QUESTION = re.compile(r"how (long|many days)|deadline|time limit|how much time", re.IGNORECASE)


def _stems(question: str) -> set[str]:
    stems = {_stem(t) for t in _query_terms(question)}
    if DURATION_QUESTION.search(question):  # "how long do I have" is asking about the window in days
        stems |= {"windo", "days"}
    return stems


def _evidence_sentences(question: str, hits: list[PolicyHit], limit: int = 4) -> list[str]:
    terms = _stems(question)
    scored: list[tuple[float, str]] = []
    for hit in hits:
        for sentence in _sentences(hit.text):
            sentence_terms = {_stem(t) for t in _tokens(sentence.lower())}
            overlap = terms & sentence_terms
            has_number = bool(NUMBER.search(sentence))
            # A number only counts when the sentence is about the question; otherwise any stray figure wins.
            score = len(overlap) + (0.75 if has_number and len(overlap) >= 2 else 0.0)
            if any(term in hit.document_slug for term in _query_terms(question)):
                score += 0.5
            if len(overlap) >= 2 or (overlap and has_number):
                scored.append((score, sentence))
    selected: list[str] = []
    seen: set[str] = set()
    for _, sentence in sorted(scored, key=lambda item: item[0], reverse=True):
        if sentence not in seen:
            selected.append(sentence)
            seen.add(sentence)
        if len(selected) >= limit:
            break
    # Overlapping chunks repeat text: drop a sentence that is only a piece of another selected one.
    return [x for x in selected if not any(x != y and x in y for y in selected)]


def _cite(sentences: list[str], hits: list[PolicyHit]) -> list[PolicyCitation]:
    """Cite the chunk each sentence was quoted from, in order, without repeats."""
    cited: dict[tuple[str, int], PolicyCitation] = {}
    for sentence in sentences:
        for hit in hits:
            if sentence in hit.text:
                cited.setdefault((hit.document_slug, hit.chunk_id), PolicyCitation(
                    document_slug=hit.document_slug, title=hit.title, chunk_id=hit.chunk_id))
                break
    return list(cited.values())


def _grounded(answer: str, evidence: list[str]) -> tuple[bool, list[str]]:
    evidence_text = " ".join(evidence)
    unsupported = [n for n in NUMBER.findall(answer) if n not in evidence_text]
    return not unsupported and bool(evidence), unsupported


class PolicyAgent:
    def __init__(self, retriever: HybridPolicyRetriever):
        self.retriever = retriever

    @classmethod
    def local(cls) -> "PolicyAgent":
        return cls(HybridPolicyRetriever(PolicyIndex.from_settings()))

    def answer(self, question: str, limit: int = 5, category: str | None = None) -> PolicyAnswer:
        hits = self.retriever.retrieve(question, limit=limit, category=category)
        # Category addenda deliberately conflict with the baseline policy, so anchor the evidence on the
        # top-ranked document; only widen to other documents when it cannot supply enough sentences.
        anchor = category_slug(category) if category else None
        anchor_slug = anchor if any(h.document_slug == anchor for h in hits) else (hits[0].document_slug if hits else None)
        primary = [h for h in hits if h.document_slug == anchor_slug]
        evidence = _evidence_sentences(question, primary)
        if not evidence:  # conversational wording: fall back to the primary document's figure-bearing sentences
            evidence = [s for h in primary for s in _sentences(h.text) if NUMBER.search(s)
                        and _stems(question) & {_stem(t) for t in _tokens(s.lower())}][:2]
        if len(evidence) < 2:
            evidence = (evidence + [e for e in _evidence_sentences(question, hits) if e not in evidence])[:4]
        top_hits = [
            PolicyCitation(document_slug=hit.document_slug, title=hit.title, chunk_id=hit.chunk_id)
            for hit in hits[:3]
        ]
        if not evidence:
            citations = top_hits
            return PolicyAnswer(
                question=question,
                answer="I do not have enough policy evidence to answer this.",
                grounded=False,
                citations=citations,
                evidence=[],
                unsupported_claims=["no_relevant_evidence"],
            )

        citations = _cite(evidence[:3], hits) or top_hits
        answer = f"{ANSWER_PREFIX} " + " ".join(evidence[:3])
        grounded, unsupported = _grounded(answer, evidence)
        return PolicyAnswer(
            question=question,
            answer=answer,
            grounded=grounded,
            citations=citations,
            evidence=evidence,
            unsupported_claims=unsupported,
        )


def answer_policy_question(question: str) -> PolicyAnswer:
    return PolicyAgent.local().answer(question)
