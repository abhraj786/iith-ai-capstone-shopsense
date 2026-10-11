"""Grounded policy-answer agent (M4).

This agent is intentionally evidence-first: it retrieves policy chunks, extracts relevant
sentences, and refuses unsupported answers instead of inventing windows, amounts, or routes.
"""

import re

from capstone.rag.hybrid import HybridPolicyRetriever
from capstone.rag.policy_index import PolicyHit, PolicyIndex, _tokens
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
    parts = [p.strip(" -*") for p in SENTENCE_SPLIT.split(text) if p.strip(" -*")]
    return [p for p in parts if len(p.split()) >= 5]


def _evidence_sentences(question: str, hits: list[PolicyHit], limit: int = 4) -> list[str]:
    terms = _query_terms(question)
    scored: list[tuple[float, str]] = []
    for hit in hits:
        for sentence in _sentences(hit.text):
            sentence_terms = set(_tokens(sentence.lower()))
            overlap = terms & sentence_terms
            has_number = bool(NUMBER.search(sentence))
            score = len(overlap) + (0.75 if has_number else 0.0)
            if any(term in hit.document_slug for term in terms):
                score += 0.5
            if overlap or has_number:
                scored.append((score, sentence))
    selected: list[str] = []
    seen: set[str] = set()
    for _, sentence in sorted(scored, key=lambda item: item[0], reverse=True):
        if sentence not in seen:
            selected.append(sentence)
            seen.add(sentence)
        if len(selected) >= limit:
            break
    return selected


def _grounded(answer: str, evidence: list[str]) -> tuple[bool, list[str]]:
    evidence_text = " ".join(evidence)
    unsupported = [n for n in NUMBER.findall(answer) if n not in evidence_text]
    return not unsupported and bool(evidence), unsupported


class PolicyAgent:
    def __init__(self, retriever: HybridPolicyRetriever):
        self.retriever = retriever

    @classmethod
    def local(cls) -> "PolicyAgent":
        return cls(HybridPolicyRetriever(PolicyIndex.local()))

    def answer(self, question: str, limit: int = 5) -> PolicyAnswer:
        hits = self.retriever.retrieve(question, limit=limit)
        evidence = _evidence_sentences(question, hits)
        citations = [
            PolicyCitation(document_slug=hit.document_slug, title=hit.title, chunk_id=hit.chunk_id)
            for hit in hits[:3]
        ]
        if not evidence:
            return PolicyAnswer(
                question=question,
                answer="I do not have enough policy evidence to answer this.",
                grounded=False,
                citations=citations,
                evidence=[],
                unsupported_claims=["no_relevant_evidence"],
            )

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
