"""M6 multi-agent team for ShopSense ticket resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from capstone.agents.action_agent import plan_action
from capstone.agents.intake_agent import parse_ticket
from capstone.agents.policy_agent import PolicyAgent
from capstone.llm.client import LLMClient
from capstone.mcp.client import MCPShopSenseToolGateway
from capstone.mcp.tools import ShopSenseToolGateway
from capstone.memory.store import CustomerMemoryStore, get_memory_store
from capstone.rag.hybrid import HybridPolicyRetriever
from capstone.rag.policy_index import PolicyIndex
from capstone.schemas.actions import ActionProposal, RecommendedAction
from capstone.schemas.intake import SupportTicket
from capstone.settings import get_settings
from capstone.tools.repository import Repository, get_repository


class AgentStep(BaseModel):
    agent: str
    summary: str
    output: dict[str, Any] = Field(default_factory=dict)


class TeamResult(BaseModel):
    channel: str
    customer_ref: str
    ticket: dict[str, Any]
    policy_answer: dict[str, Any]
    action_proposal: dict[str, Any]
    memory_context: dict[str, Any]
    escalation_review: dict[str, Any]
    steps: list[AgentStep]


@dataclass
class MultiAgentTeam:
    client: LLMClient = field(default_factory=LLMClient)
    repo: Repository = field(default_factory=get_repository)
    memory_store: CustomerMemoryStore = field(default_factory=get_memory_store)
    policy_index: PolicyIndex | None = None
    policy_agent: PolicyAgent | None = None
    tool_gateway: ShopSenseToolGateway | MCPShopSenseToolGateway | None = None
    use_mcp_tools: bool = False

    def __post_init__(self) -> None:
        if self.policy_index is None:
            self.policy_index = PolicyIndex.from_settings()
            if not self.policy_index.client.collection_exists(self.policy_index.collection_name):
                self.policy_index.build(recreate=False)
        if self.policy_agent is None:
            self.policy_agent = PolicyAgent(HybridPolicyRetriever(self.policy_index))
        if self.tool_gateway is None:
            self.tool_gateway = MCPShopSenseToolGateway() if self.use_mcp_tools else ShopSenseToolGateway(self.repo)

    def resolve(
        self,
        *,
        raw_text: str,
        channel: str,
        customer_ref: str,
        today: str,
        execute_actions: bool = False,
    ) -> TeamResult:
        run_date = date.fromisoformat(today)
        steps: list[AgentStep] = []

        ticket = parse_ticket(
            self.client,
            raw_text,
            channel=channel,
            auto_refund_cap_inr=2000,
            repeat_contact_threshold=3,
        )
        steps.append(AgentStep(
            agent="Triage Agent",
            summary="Parsed raw channel text into a validated SupportTicket.",
            output=ticket.model_dump(mode="json"),
        ))

        memory_context = self.memory_store.customer_context(customer_ref)
        steps.append(AgentStep(
            agent="Memory Agent",
            summary="Loaded persistent per-customer support context.",
            output=memory_context,
        ))

        policy_query = _policy_query(ticket)
        policy_answer = self.policy_agent.answer(policy_query)
        steps.append(AgentStep(
            agent="Policy RAG Agent",
            summary="Answered policy question with citations before action planning.",
            output=policy_answer.model_dump(mode="json"),
        ))

        proposal = plan_action(self.repo, ticket, customer_ref, run_date, execute=False)
        self._apply_tool_result(proposal, customer_ref, ticket.order_ref, today, execute_actions)
        steps.append(AgentStep(
            agent="Order-Actions Agent",
            summary=f"Planned or executed the safest deterministic tool action via {self.tool_transport}.",
            output=proposal.model_dump(mode="json"),
        ))

        review = self._review(ticket, proposal)
        steps.append(AgentStep(
            agent="Escalation Reviewer Agent",
            summary="Checked whether the case may be auto-resolved or must wait for a human.",
            output=review,
        ))

        self.memory_store.append_ticket(
            customer_ref,
            ticket,
            proposal,
            channel=channel,
            received_at=today,
        )
        updated_memory = self.memory_store.customer_context(customer_ref)

        return TeamResult(
            channel=channel,
            customer_ref=customer_ref,
            ticket=ticket.model_dump(mode="json"),
            policy_answer=policy_answer.model_dump(mode="json"),
            action_proposal=proposal.model_dump(mode="json"),
            memory_context=updated_memory,
            escalation_review=review,
            steps=steps,
        )

    @property
    def tool_transport(self) -> str:
        return "mcp" if isinstance(self.tool_gateway, MCPShopSenseToolGateway) else "python"

    def _apply_tool_result(
        self,
        proposal: ActionProposal,
        customer_ref: str,
        order_ref: str | None,
        today: str,
        execute_actions: bool,
    ) -> None:
        if not proposal.tool_name:
            return
        if proposal.tool_name == "track_shipment" and order_ref:
            proposal.tool_result = self.tool_gateway.track_shipment(customer_ref, order_ref)
            return
        if not execute_actions:
            return
        proposal.executed = True
        if proposal.tool_name == "issue_refund":
            proposal.tool_result = self.tool_gateway.issue_refund(
                customer_ref=customer_ref,
                order_ref=proposal.tool_args["order_ref"],
                reason_code=proposal.tool_args["reason_code"],
                today=today,
                approved_by=proposal.tool_args.get("approved_by", "auto"),
            )
        elif proposal.tool_name == "create_replacement":
            proposal.tool_result = self.tool_gateway.create_replacement(
                customer_ref=customer_ref,
                order_ref=proposal.tool_args["order_ref"],
                reason=proposal.tool_args["reason"],
                today=today,
                approved_by=proposal.tool_args.get("approved_by", "auto"),
            )
        elif proposal.tool_name == "flag_for_human":
            proposal.tool_result = self.tool_gateway.flag_for_human(
                customer_ref=customer_ref,
                order_ref=proposal.tool_args.get("order_ref"),
                trigger=proposal.tool_args["trigger"],
                note=proposal.tool_args.get("note", ""),
            )
        if proposal.tool_result and not proposal.tool_result.get("ok", True):
            proposal.tool_error = proposal.tool_result.get("error")
            proposal.executed = False

    @staticmethod
    def _review(ticket: SupportTicket, proposal: ActionProposal) -> dict[str, Any]:
        if proposal.recommended_action is RecommendedAction.request_missing_info:
            return {
                "decision": "ask_customer",
                "requires_human": False,
                "reason": "Missing fields must be collected before action.",
            }
        if proposal.requires_human:
            return {
                "decision": "human_review",
                "requires_human": True,
                "reason": proposal.tool_args.get("trigger") or proposal.reason_code or "requires_human",
            }
        return {
            "decision": "auto_resolve",
            "requires_human": False,
            "reason": "Low-risk deterministic action path.",
        }


def _policy_query(ticket: SupportTicket) -> str:
    return " ".join([
        ticket.issue_type.value,
        ticket.summary,
        " ".join(signal.value for signal in ticket.escalation_signals),
    ]).strip()

