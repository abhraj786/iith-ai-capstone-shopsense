"""M6 multi-agent team for ShopSense ticket resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from capstone.agents.action_agent import plan_action
from capstone.agents.intake_agent import parse_ticket
from capstone.agents.policy_agent import PolicyAgent
from capstone.guardrails import apply_guardrails
from capstone.llm.client import LLMClient
from capstone.mcp.client import MCPShopSenseToolGateway
from capstone.tools.lookups import order_category
from capstone.mcp.tools import ShopSenseToolGateway
from capstone.memory.store import CustomerMemoryStore, get_memory_store
from capstone.observability.tracing import TraceRecorder, get_trace_recorder
from capstone.rag.hybrid import HybridPolicyRetriever
from capstone.rag.policy_index import PolicyIndex
from capstone.reliability.tools import ReliableToolGateway
from capstone.schemas.actions import ActionProposal, RecommendedAction
from capstone.schemas.intake import SupportTicket
from capstone.settings import get_settings
from capstone.tools import actions
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
    guardrails: dict[str, Any] = Field(default_factory=dict)
    steps: list[AgentStep]
    trace: dict[str, Any] = Field(default_factory=dict)


@dataclass
class MultiAgentTeam:
    client: LLMClient = field(default_factory=LLMClient)
    repo: Repository = field(default_factory=get_repository)
    memory_store: CustomerMemoryStore = field(default_factory=get_memory_store)
    policy_index: PolicyIndex | None = None
    policy_agent: PolicyAgent | None = None
    tool_gateway: ShopSenseToolGateway | MCPShopSenseToolGateway | None = None
    use_mcp_tools: bool = False
    reliable_tools: bool = True
    tracer: TraceRecorder | None = None

    def __post_init__(self) -> None:
        if self.policy_index is None:
            self.policy_index = PolicyIndex.from_settings()
            if not self.policy_index.client.collection_exists(self.policy_index.collection_name):
                self.policy_index.build(recreate=False)
        if self.policy_agent is None:
            self.policy_agent = PolicyAgent(HybridPolicyRetriever(self.policy_index))
        if self.tool_gateway is None:
            self.tool_gateway = MCPShopSenseToolGateway() if self.use_mcp_tools else ShopSenseToolGateway(self.repo)
        if self.reliable_tools and not isinstance(self.tool_gateway, ReliableToolGateway):
            self.tool_gateway = ReliableToolGateway(self.tool_gateway)
        if self.tracer is None:
            self.tracer = get_trace_recorder()

    def resolve(
        self,
        *,
        raw_text: str,
        channel: str,
        customer_ref: str,
        today: str,
        execute_actions: bool = False,
        session_id: str | None = None,
        user_id: str | None = None,
        tags: list[str] | None = None,
    ) -> TeamResult:
        run_date = date.fromisoformat(today)
        steps: list[AgentStep] = []
        trace = self.tracer.start_trace(
            "shopsense.ticket_resolution",
            metadata={"channel": channel, "customer_ref": customer_ref, "tool_transport": self.tool_transport},
            session_id=session_id,
            user_id=user_id or customer_ref,
            tags=tags or ["shopsense", "m7", channel],
        )

        with trace.span("Triage Agent", metadata={"channel": channel}):
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

        with trace.span("Memory Agent", metadata={"customer_ref": customer_ref}):
            memory_context = self.memory_store.customer_context(customer_ref)
        steps.append(AgentStep(
            agent="Memory Agent",
            summary="Loaded persistent per-customer support context.",
            output=memory_context,
        ))

        with trace.span("Policy RAG Agent"):
            policy_query = _policy_query(ticket)
            with trace.span("policy.hybrid_retrieval", metadata={"query": policy_query}):
                policy_answer = self.policy_agent.answer(
                    policy_query, category=order_category(self.repo, customer_ref, ticket.order_ref))
        steps.append(AgentStep(
            agent="Policy RAG Agent",
            summary="Answered policy question with citations before action planning.",
            output=policy_answer.model_dump(mode="json"),
        ))

        with trace.span("Order-Actions Agent", metadata={"transport": self.tool_transport}) as span:
            proposal = plan_action(self.repo, ticket, customer_ref, run_date, execute=False)
            self._apply_tool_result(proposal, customer_ref, ticket.order_ref, today, execute_actions, trace)
            proposal, guardrails = apply_guardrails(ticket, proposal, policy_answer)
            span.set_output(proposal.model_dump(mode="json"))
        steps.append(AgentStep(
            agent="Order-Actions Agent",
            summary=f"Planned or executed the safest deterministic tool action via {self.tool_transport}.",
            output=proposal.model_dump(mode="json"),
        ))

        with trace.span("Escalation Reviewer Agent"):
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

        trace_result = trace.end(output={"decision": review["decision"], "tool_name": proposal.tool_name})

        return TeamResult(
            channel=channel,
            customer_ref=customer_ref,
            ticket=ticket.model_dump(mode="json"),
            policy_answer=policy_answer.model_dump(mode="json"),
            action_proposal=proposal.model_dump(mode="json"),
            memory_context=updated_memory,
            escalation_review=review,
            guardrails=guardrails.model_dump(mode="json"),
            steps=steps,
            trace=trace_result,
        )

    @property
    def tool_transport(self) -> str:
        gateway = self.tool_gateway.gateway if isinstance(self.tool_gateway, ReliableToolGateway) else self.tool_gateway
        return "mcp" if isinstance(gateway, MCPShopSenseToolGateway) else "python"

    def _apply_tool_result(
        self,
        proposal: ActionProposal,
        customer_ref: str,
        order_ref: str | None,
        today: str,
        execute_actions: bool,
        trace,
    ) -> None:
        if not proposal.tool_name:
            return
        if proposal.tool_name == "track_shipment" and order_ref:
            with trace.span("tool.track_shipment", metadata={"order_ref": order_ref}) as span:
                proposal.tool_result = self.tool_gateway.track_shipment(customer_ref, order_ref)
                span.set_output(proposal.tool_result)
        elif not execute_actions:
            return
        else:
            proposal.executed = True
            if proposal.tool_name == "issue_refund":
                with trace.span("tool.issue_refund", metadata={"order_ref": proposal.tool_args["order_ref"]}) as span:
                    proposal.tool_result = self.tool_gateway.issue_refund(
                        customer_ref=customer_ref,
                        order_ref=proposal.tool_args["order_ref"],
                        reason_code=proposal.tool_args["reason_code"],
                        today=today,
                        approved_by=proposal.tool_args.get("approved_by", "auto"),
                    )
                    span.set_output(proposal.tool_result)
            elif proposal.tool_name == "create_replacement":
                with trace.span("tool.create_replacement", metadata={"order_ref": proposal.tool_args["order_ref"]}) as span:
                    proposal.tool_result = self.tool_gateway.create_replacement(
                        customer_ref=customer_ref,
                        order_ref=proposal.tool_args["order_ref"],
                        reason=proposal.tool_args["reason"],
                        today=today,
                        approved_by=proposal.tool_args.get("approved_by", "auto"),
                    )
                    span.set_output(proposal.tool_result)
            elif proposal.tool_name == "flag_for_human":
                with trace.span("tool.flag_for_human", metadata={"trigger": proposal.tool_args["trigger"]}) as span:
                    proposal.tool_result = self.tool_gateway.flag_for_human(
                        customer_ref=customer_ref,
                        order_ref=proposal.tool_args.get("order_ref"),
                        trigger=proposal.tool_args["trigger"],
                        note=proposal.tool_args.get("note", ""),
                    )
                    span.set_output(proposal.tool_result)
        if proposal.tool_result and not proposal.tool_result.get("ok", True):
            proposal.tool_error = proposal.tool_result.get("error")
            proposal.executed = False
            if proposal.tool_result.get("reliability", {}).get("fallback") == "human_queue":
                proposal.requires_human = True
                proposal.recommended_action = RecommendedAction.human_review
                proposal.tool_name = "flag_for_human"
                proposal.tool_args = {
                    "customer_ref": customer_ref,
                    "order_ref": order_ref,
                    "trigger": "human_requested",
                    "note": f"Tool failure fallback: {proposal.tool_error}",
                }
                proposal.tool_result = actions.flag_for_human(
                    self.repo,
                    customer_ref,
                    order_ref,
                    "human_requested",
                    proposal.tool_args["note"],
                )

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

