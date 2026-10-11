"""M5 LangGraph workflow for ShopSense ticket resolution.

The graph connects existing milestone modules instead of duplicating their logic:
triage (M1) -> memory (M3) -> policy check (M4) -> action planning/execution (M2)
-> conditional routing for auto-resolution or human approval.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from capstone.agents.action_agent import plan_action
from capstone.agents.intake_agent import parse_ticket
from capstone.agents.policy_agent import PolicyAgent
from capstone.llm.client import LLMClient
from capstone.memory.store import CustomerMemoryStore, get_memory_store
from capstone.rag.hybrid import HybridPolicyRetriever
from capstone.rag.policy_index import PolicyIndex
from capstone.schemas.actions import ActionProposal, RecommendedAction
from capstone.schemas.intake import Sentiment, SupportTicket, Urgency
from capstone.settings import PROJECT_ROOT, get_settings
from capstone.tools.repository import Repository, get_repository


class TicketWorkflowState(TypedDict, total=False):
    run_id: str
    raw_text: str
    channel: str
    customer_ref: str
    today: str
    execute_actions: bool
    ticket: dict[str, Any]
    memory_context: dict[str, Any]
    policy_answer: dict[str, Any]
    action_proposal: dict[str, Any]
    route: str
    status: str
    final_message: str
    checkpoints: list[str]


class WorkflowCheckpointStore:
    """Small JSON checkpoint store for inspectable workflow state."""

    def __init__(self, root: Path | None = None):
        settings = get_settings()
        self.root = Path(root or (PROJECT_ROOT / settings.runtime_root / "workflow_checkpoints"))
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, run_id: str, node: str, state: TicketWorkflowState) -> str:
        run_dir = self.root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / f"{len(list(run_dir.glob('*.json'))):02d}_{node}.json"
        path.write_text(json.dumps(state, indent=2, sort_keys=True))
        return str(path)


class WorkflowDeps:
    def __init__(
        self,
        *,
        client: LLMClient | None = None,
        repo: Repository | None = None,
        memory_store: CustomerMemoryStore | None = None,
        policy_index: PolicyIndex | None = None,
        policy_agent: PolicyAgent | None = None,
        checkpointer: WorkflowCheckpointStore | None = None,
    ):
        self.client = client or LLMClient()
        self.repo = repo or get_repository()
        self.memory_store = memory_store or get_memory_store()
        self.policy_index = policy_index or PolicyIndex.from_settings()
        if not self.policy_index.client.collection_exists(self.policy_index.collection_name):
            self.policy_index.build(recreate=False)
        self.policy_agent = policy_agent or PolicyAgent(HybridPolicyRetriever(self.policy_index))
        self.checkpointer = checkpointer or WorkflowCheckpointStore()


def _checkpoint(deps: WorkflowDeps, node: str, state: TicketWorkflowState) -> TicketWorkflowState:
    checkpoints = [*state.get("checkpoints", [])]
    checkpoints.append(deps.checkpointer.save(state["run_id"], node, state))
    return {**state, "checkpoints": checkpoints}


def _policy_query(ticket: SupportTicket, proposal: ActionProposal | None = None) -> str:
    parts = [
        ticket.issue_type.value,
        ticket.summary,
        " ".join(signal.value for signal in ticket.escalation_signals),
    ]
    if proposal:
        parts.append(proposal.explanation)
    return " ".join(part for part in parts if part)


def _workflow_route(state: TicketWorkflowState) -> Literal["missing_info", "human_interrupt", "auto_execute"]:
    proposal = ActionProposal.model_validate(state["action_proposal"])
    ticket = SupportTicket.model_validate(state["ticket"])
    if proposal.recommended_action is RecommendedAction.request_missing_info:
        return "missing_info"
    if (
        proposal.requires_human
        or proposal.recommended_action is RecommendedAction.human_review
        or ticket.sentiment in {Sentiment.angry, Sentiment.distressed}
        or ticket.urgency is Urgency.critical
    ):
        return "human_interrupt"
    return "auto_execute"


def build_workflow(deps: WorkflowDeps | None = None):
    deps = deps or WorkflowDeps()

    def triage_node(state: TicketWorkflowState) -> TicketWorkflowState:
        ticket = parse_ticket(
            deps.client,
            state["raw_text"],
            state.get("channel"),
            auto_refund_cap_inr=2000,
            repeat_contact_threshold=3,
        )
        next_state: TicketWorkflowState = {**state, "ticket": ticket.model_dump(mode="json")}
        return _checkpoint(deps, "triage", next_state)

    def memory_node(state: TicketWorkflowState) -> TicketWorkflowState:
        ticket = SupportTicket.model_validate(state["ticket"])
        deps.memory_store.append_ticket(
            state["customer_ref"],
            ticket,
            channel=state.get("channel"),
            received_at=state.get("today"),
        )
        context = deps.memory_store.customer_context(state["customer_ref"])
        next_state: TicketWorkflowState = {**state, "memory_context": context}
        return _checkpoint(deps, "memory", next_state)

    def policy_node(state: TicketWorkflowState) -> TicketWorkflowState:
        ticket = SupportTicket.model_validate(state["ticket"])
        answer = deps.policy_agent.answer(_policy_query(ticket))
        next_state: TicketWorkflowState = {**state, "policy_answer": answer.model_dump(mode="json")}
        return _checkpoint(deps, "policy_check", next_state)

    def action_node(state: TicketWorkflowState) -> TicketWorkflowState:
        ticket = SupportTicket.model_validate(state["ticket"])
        proposal = plan_action(
            deps.repo,
            ticket,
            customer_ref=state["customer_ref"],
            today=date.fromisoformat(state["today"]),
            execute=False,
        )
        next_state: TicketWorkflowState = {
            **state,
            "action_proposal": proposal.model_dump(mode="json"),
        }
        return _checkpoint(deps, "action_plan", next_state)

    def missing_info_node(state: TicketWorkflowState) -> TicketWorkflowState:
        final = "Missing required information; ask the customer for the order reference/details."
        next_state: TicketWorkflowState = {
            **state,
            "route": "missing_info",
            "status": "needs_customer_info",
            "final_message": final,
        }
        return _checkpoint(deps, "missing_info", next_state)

    def human_interrupt_node(state: TicketWorkflowState) -> TicketWorkflowState:
        proposal = ActionProposal.model_validate(state["action_proposal"])
        ticket = SupportTicket.model_validate(state["ticket"])
        if state.get("execute_actions", False):
            proposal = plan_action(
                deps.repo,
                ticket,
                customer_ref=state["customer_ref"],
                today=date.fromisoformat(state["today"]),
                execute=True,
            )
        final = "Human approval required before resolution."
        next_state: TicketWorkflowState = {
            **state,
            "route": "human_interrupt",
            "status": "human_approval_required",
            "action_proposal": proposal.model_dump(mode="json"),
            "final_message": final,
        }
        return _checkpoint(deps, "human_interrupt", next_state)

    def auto_execute_node(state: TicketWorkflowState) -> TicketWorkflowState:
        ticket = SupportTicket.model_validate(state["ticket"])
        proposal = plan_action(
            deps.repo,
            ticket,
            customer_ref=state["customer_ref"],
            today=date.fromisoformat(state["today"]),
            execute=state.get("execute_actions", False),
        )
        status = "auto_resolved_executed" if proposal.executed else "auto_resolved_proposed"
        final = "Low-risk case auto-resolved." if proposal.executed else "Low-risk case ready for auto-resolution."
        next_state: TicketWorkflowState = {
            **state,
            "route": "auto_execute",
            "status": status,
            "action_proposal": proposal.model_dump(mode="json"),
            "final_message": final,
        }
        return _checkpoint(deps, "auto_execute", next_state)

    graph = StateGraph(TicketWorkflowState)
    graph.add_node("triage", triage_node)
    graph.add_node("memory", memory_node)
    graph.add_node("policy_check", policy_node)
    graph.add_node("action_plan", action_node)
    graph.add_node("missing_info", missing_info_node)
    graph.add_node("human_interrupt", human_interrupt_node)
    graph.add_node("auto_execute", auto_execute_node)
    graph.set_entry_point("triage")
    graph.add_edge("triage", "memory")
    graph.add_edge("memory", "policy_check")
    graph.add_edge("policy_check", "action_plan")
    graph.add_conditional_edges(
        "action_plan",
        _workflow_route,
        {
            "missing_info": "missing_info",
            "human_interrupt": "human_interrupt",
            "auto_execute": "auto_execute",
        },
    )
    graph.add_edge("missing_info", END)
    graph.add_edge("human_interrupt", END)
    graph.add_edge("auto_execute", END)
    return graph.compile()


def run_ticket_workflow(
    *,
    raw_text: str,
    channel: str,
    customer_ref: str,
    today: str,
    run_id: str,
    execute_actions: bool = False,
    deps: WorkflowDeps | None = None,
) -> TicketWorkflowState:
    app = build_workflow(deps)
    initial: TicketWorkflowState = {
        "run_id": run_id,
        "raw_text": raw_text,
        "channel": channel,
        "customer_ref": customer_ref,
        "today": today,
        "execute_actions": execute_actions,
        "checkpoints": [],
    }
    return app.invoke(initial)
