"""FastAPI packaging for the M8 ShopSense demo endpoint."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient

from capstone.agents.action_agent import plan_action
from capstone.agents.intake_agent import apply_contact_count
from capstone.agents.policy_agent import PolicyAgent
from capstone.guardrails import apply_guardrails, safe_policy_answer
from capstone.memory.store import get_memory_store
from capstone.rag.hybrid import HybridPolicyRetriever
from capstone.rag.policy_index import PolicyIndex
from capstone.schemas.intake import SupportTicket
from capstone.team.multi_agent import MultiAgentTeam
from capstone.settings import PROJECT_ROOT, get_settings
from capstone.tools.lookups import order_category
from capstone.tools.repository import get_repository


class ChatRequest(BaseModel):
    raw_text: str = Field(..., min_length=1)
    channel: str = "chat"
    customer_ref: str
    today: str = Field(default_factory=lambda: date.today().isoformat())
    execute_actions: bool = False
    support_ticket: SupportTicket | None = None


class ChatResponse(BaseModel):
    channel: str
    customer_ref: str
    ticket: dict[str, Any]
    policy_answer: dict[str, Any]
    action_proposal: dict[str, Any]
    guardrails: dict[str, Any]
    memory_context: dict[str, Any] = Field(default_factory=dict)
    escalation_review: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(default_factory=dict)


app = FastAPI(title="ShopSense Customer Care Assistant", version="0.8.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "milestone": "M8"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    if request.support_ticket is not None:
        return _chat_from_ticket(request)

    result = MultiAgentTeam(use_mcp_tools=False).resolve(
        raw_text=request.raw_text,
        channel=request.channel,
        customer_ref=request.customer_ref,
        today=request.today,
        execute_actions=request.execute_actions,
    )
    guardrails = result.guardrails
    policy_answer = safe_policy_answer(result.policy_answer, _guardrail_model(guardrails))
    return ChatResponse(
        channel=result.channel,
        customer_ref=result.customer_ref,
        ticket=result.ticket,
        policy_answer=policy_answer,
        action_proposal=result.action_proposal,
        guardrails=guardrails,
        memory_context=result.memory_context,
        escalation_review=result.escalation_review,
        trace=result.trace,
    )


def _chat_from_ticket(request: ChatRequest) -> ChatResponse:
    assert request.support_ticket is not None

    repo = get_repository()
    memory = get_memory_store()
    ticket = request.support_ticket.model_copy(deep=True)
    try:
        prior = memory.prior_contacts(request.customer_ref, ticket.order_ref, ticket.issue_type.value,
                                     request.today, request.channel)
    except (OSError, ValueError):  # unreadable memory must not block the ticket
        prior = 0
    apply_contact_count(ticket, prior, 3)
    policy_answer = _local_policy_agent().answer(
        _policy_query(ticket), category=order_category(repo, request.customer_ref, ticket.order_ref))
    proposal = plan_action(repo, ticket, request.customer_ref, date.fromisoformat(request.today), execute=False)
    proposal, guardrails = apply_guardrails(ticket, proposal, policy_answer)
    memory_context = {}
    try:
        memory.append_ticket(customer_ref=request.customer_ref, ticket=ticket, action=proposal,
                             channel=request.channel, received_at=request.today)
        memory_context = memory.customer_context(request.customer_ref)
    except OSError:
        memory_context = {"customer_ref": request.customer_ref, "memory_persistence": "unavailable"}
    policy_dict = safe_policy_answer(policy_answer.model_dump(mode="json"), guardrails)
    review = {
        "decision": "human_review" if proposal.requires_human else "auto_resolve",
        "requires_human": proposal.requires_human,
        "reason": proposal.tool_args.get("trigger") or proposal.reason_code or "guarded_response",
    }
    return ChatResponse(
        channel=request.channel,
        customer_ref=request.customer_ref,
        ticket=ticket.model_dump(mode="json"),
        policy_answer=policy_dict,
        action_proposal=proposal.model_dump(mode="json"),
        guardrails=guardrails.model_dump(mode="json"),
        memory_context=memory_context,
        escalation_review=review,
        trace={},
    )


def _policy_query(ticket: SupportTicket) -> str:
    return " ".join([
        ticket.issue_type.value,
        ticket.summary,
        " ".join(signal.value for signal in ticket.escalation_signals),
    ]).strip()


def _local_policy_agent() -> PolicyAgent:
    settings = get_settings()
    index = PolicyIndex(QdrantClient(":memory:"), PROJECT_ROOT / settings.data_root / settings.domain)
    index.build(recreate=False)
    return PolicyAgent(HybridPolicyRetriever(index))


def _guardrail_model(payload: dict[str, Any]):
    from capstone.guardrails import GuardrailResult

    return GuardrailResult.model_validate(payload)
