"""Policy RAG answer schemas (M4)."""

from pydantic import BaseModel, Field


class PolicyCitation(BaseModel):
    document_slug: str
    title: str
    chunk_id: int


class PolicyAnswer(BaseModel):
    question: str
    answer: str
    grounded: bool
    citations: list[PolicyCitation] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
