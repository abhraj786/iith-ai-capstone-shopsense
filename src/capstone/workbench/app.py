"""Local UI for testing ShopSense milestones end to end."""

from __future__ import annotations

import json
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from pydantic import ValidationError

from capstone.agents.action_agent import plan_action
from capstone.agents.intake_agent import parse_ticket
from capstone.agents.policy_agent import PolicyAgent
from capstone.llm.client import LLMClient
from capstone.mcp.client import MCPShopSenseToolGateway, ShopSenseMCPClient
from capstone.memory.store import CustomerMemoryStore, get_memory_store
from capstone.rag.hybrid import HybridPolicyRetriever
from capstone.rag.policy_index import PolicyIndex
from capstone.schemas.intake import SupportTicket
from capstone.settings import PROJECT_ROOT, get_settings
from capstone.tools import lookups
from capstone.tools.calculators import delivered_on
from capstone.tools.repository import Repository, get_repository
from capstone.team.multi_agent import MultiAgentTeam
from capstone.workflow.graph import (
    WorkflowDeps,
    resume_ticket_workflow,
    run_ticket_workflow,
)


DEFAULT_RAW_TEXT = (
    "Dear Support Team, This is my second time writing regarding order KW-O-000950 "
    "for the Turquoise Nation Home & Kitchen item. It was delivered 4 days late on "
    "2026-02-18 and frankly I am appalled by the poor service. I demand a full refund "
    "of 6,499 INR immediately or I will be filing a formal complaint with the National "
    "Consumer Helpline and pursuing legal action."
)


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ShopSense Milestone Workbench</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --ink: #1f2933;
      --muted: #667085;
      --line: #d7dee8;
      --accent: #1167b1;
      --accent-2: #0b7a75;
      --danger: #b42318;
      --soft: #eef4ff;
      --radius: 8px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }
    header {
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      padding: 18px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    h1 { margin: 0; font-size: 22px; letter-spacing: 0; }
    .sub { color: var(--muted); font-size: 14px; margin-top: 3px; }
    main {
      display: grid;
      grid-template-columns: minmax(340px, 0.85fr) minmax(520px, 1.15fr);
      gap: 18px;
      padding: 18px 24px 28px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 16px;
      min-width: 0;
    }
    .section-title {
      margin: 0 0 12px;
      font-size: 16px;
      font-weight: 700;
    }
    label {
      display: block;
      margin: 12px 0 6px;
      color: #344054;
      font-size: 13px;
      font-weight: 650;
    }
    input, select, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 11px;
      font: inherit;
      background: #fff;
      color: var(--ink);
    }
    textarea {
      min-height: 220px;
      resize: vertical;
      line-height: 1.45;
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      margin-top: 14px;
    }
    button {
      border: 1px solid var(--accent);
      background: var(--accent);
      color: #fff;
      border-radius: 6px;
      padding: 10px 13px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    button.secondary {
      background: #fff;
      color: var(--accent);
    }
    .check {
      display: inline-flex;
      gap: 8px;
      align-items: center;
      color: #344054;
      font-size: 14px;
      margin-left: auto;
    }
    .check input { width: 16px; height: 16px; }
    .status {
      min-height: 28px;
      margin-top: 12px;
      color: var(--muted);
      font-size: 14px;
    }
    .status.error { color: var(--danger); }
    .outputs {
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
    }
    .module {
      border: 1px solid var(--line);
      border-radius: var(--radius);
      overflow: hidden;
      background: #fff;
    }
    .module-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      background: var(--soft);
      border-bottom: 1px solid var(--line);
      padding: 10px 12px;
      font-weight: 750;
    }
    .badge {
      border-radius: 999px;
      padding: 3px 9px;
      font-size: 12px;
      color: #064e3b;
      background: #d1fae5;
      white-space: nowrap;
    }
    .badge.pending { color: #344054; background: #eef2f6; }
    pre {
      margin: 0;
      padding: 12px;
      min-height: 96px;
      max-height: 360px;
      overflow: auto;
      font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      white-space: pre-wrap;
      word-break: break-word;
    }
    @media (max-width: 920px) {
      header { align-items: flex-start; flex-direction: column; }
      main { grid-template-columns: 1fr; padding: 14px; }
      .row { grid-template-columns: 1fr; }
      .check { margin-left: 0; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>ShopSense Milestone Workbench</h1>
      <div class="sub">Run the ShopSense milestones from one local tester UI and inspect each stage.</div>
    </div>
    <div class="sub" id="serverInfo">Local test UI</div>
  </header>
  <main>
    <section>
      <h2 class="section-title">Input</h2>
      <div class="row">
        <div>
          <label for="mode">Run mode</label>
          <select id="mode">
            <option value="full">M1 + M2</option>
            <option value="m2">M2 only from JSON</option>
            <option value="m5">M5 workflow from JSON</option>
            <option value="m6">M6 multi-agent via MCP</option>
          </select>
        </div>
        <div>
          <label for="channel">Channel</label>
          <select id="channel">
            <option>email</option>
            <option>chat</option>
            <option>phone</option>
            <option>social</option>
          </select>
        </div>
      </div>
      <div class="row">
        <div>
          <label for="customerRef">Customer reference</label>
          <input id="customerRef" value="KW-C-00285" />
        </div>
        <div>
          <label for="today">Policy date</label>
          <input id="today" type="date" value="2026-03-10" />
        </div>
      </div>
      <label for="rawText">Raw customer text</label>
      <textarea id="rawText"></textarea>
      <label for="ticketJson">M2-only SupportTicket JSON</label>
      <textarea id="ticketJson" spellcheck="false"></textarea>
      <div class="toolbar">
        <button id="runBtn">Run</button>
        <button class="secondary" id="sampleBtn">Legal sample</button>
        <button class="secondary" id="autoSampleBtn">Safe sample</button>
        <label class="check"><input id="execute" type="checkbox" /> Execute mutable M2 action</label>
      </div>
      <div class="toolbar">
        <button class="secondary" id="approveBtn" disabled>Approve M5 resume</button>
        <button class="secondary" id="rejectBtn" disabled>Reject M5 resume</button>
      </div>
      <div id="status" class="status"></div>
    </section>
    <section>
      <h2 class="section-title">Milestone Output</h2>
      <div class="outputs">
        <div class="module">
          <div class="module-head"><span>M1 Intake JSON</span><span class="badge pending" id="m1Badge">Waiting</span></div>
          <pre id="m1Out">{}</pre>
        </div>
        <div class="module">
          <div class="module-head"><span>M2 Action Proposal</span><span class="badge pending" id="m2Badge">Waiting</span></div>
          <pre id="m2Out">{}</pre>
        </div>
        <div class="module">
          <div class="module-head"><span>M3 Memory + Policy Hits</span><span class="badge pending" id="m3Badge">Waiting</span></div>
          <pre id="m3Out">{}</pre>
        </div>
        <div class="module">
          <div class="module-head"><span>M4 Grounded Policy Answer</span><span class="badge pending" id="m4Badge">Waiting</span></div>
          <pre id="m4Out">{}</pre>
        </div>
        <div class="module">
          <div class="module-head"><span>M5 LangGraph Workflow</span><span class="badge pending" id="m5Badge">Waiting</span></div>
          <pre id="m5Out">{}</pre>
        </div>
        <div class="module">
          <div class="module-head"><span>M6 Multi-Agent + MCP</span><span class="badge pending" id="m6Badge">Waiting</span></div>
          <pre id="m6Out">{}</pre>
        </div>
      </div>
    </section>
  </main>
  <script>
    const rawText = document.querySelector("#rawText");
    const ticketJson = document.querySelector("#ticketJson");
    const statusEl = document.querySelector("#status");
    const m1Out = document.querySelector("#m1Out");
    const m2Out = document.querySelector("#m2Out");
    const m3Out = document.querySelector("#m3Out");
    const m4Out = document.querySelector("#m4Out");
    const m5Out = document.querySelector("#m5Out");
    const m6Out = document.querySelector("#m6Out");
    const m1Badge = document.querySelector("#m1Badge");
    const m2Badge = document.querySelector("#m2Badge");
    const m3Badge = document.querySelector("#m3Badge");
    const m4Badge = document.querySelector("#m4Badge");
    const m5Badge = document.querySelector("#m5Badge");
    const m6Badge = document.querySelector("#m6Badge");
    let currentRunId = null;

    function pretty(value) {
      return JSON.stringify(value ?? {}, null, 2);
    }

    function setStatus(text, isError = false) {
      statusEl.textContent = text;
      statusEl.className = isError ? "status error" : "status";
    }

    function setResumeEnabled(enabled) {
      document.querySelector("#approveBtn").disabled = !enabled;
      document.querySelector("#rejectBtn").disabled = !enabled;
    }

    async function loadSample(kind = "legal") {
      const res = await fetch(`/api/sample?kind=${kind}`);
      const data = await res.json();
      rawText.value = data.raw_text;
      ticketJson.value = pretty(data.ticket_json);
      document.querySelector("#customerRef").value = data.customer_ref;
      document.querySelector("#channel").value = data.channel;
      document.querySelector("#today").value = data.today;
      document.querySelector("#mode").value = kind === "auto" ? "m5" : document.querySelector("#mode").value;
      setStatus("Sample loaded.");
    }

    async function run() {
      setStatus("Running...");
      currentRunId = null;
      setResumeEnabled(false);
      m1Badge.textContent = "Running";
      m2Badge.textContent = "Waiting";
      m3Badge.textContent = "Waiting";
      m4Badge.textContent = "Waiting";
      m5Badge.textContent = "Waiting";
      m6Badge.textContent = "Waiting";
      m1Badge.className = "badge pending";
      m2Badge.className = "badge pending";
      m3Badge.className = "badge pending";
      m4Badge.className = "badge pending";
      m5Badge.className = "badge pending";
      m6Badge.className = "badge pending";
      const payload = {
        mode: document.querySelector("#mode").value,
        raw_text: rawText.value,
        ticket_json: ticketJson.value,
        channel: document.querySelector("#channel").value,
        customer_ref: document.querySelector("#customerRef").value,
        today: document.querySelector("#today").value,
        execute: document.querySelector("#execute").checked
      };
      try {
        const res = await fetch("/api/run", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) {
          setStatus(data.error || "Run failed.", true);
          m1Badge.textContent = data.stage === "m1" ? "Failed" : "Skipped";
          m2Badge.textContent = data.stage === "m2" ? "Failed" : "Skipped";
          m3Badge.textContent = data.stage === "m3" ? "Failed" : "Skipped";
          m4Badge.textContent = data.stage === "m4" ? "Failed" : "Skipped";
          m1Out.textContent = pretty(data.m1);
          m2Out.textContent = pretty(data.m2 || data);
          m3Out.textContent = pretty(data.m3 || {});
          m4Out.textContent = pretty(data.m4 || {});
          m5Out.textContent = pretty(data.m5 || {});
          m6Out.textContent = pretty(data.m6 || {});
          return;
        }
        m1Out.textContent = pretty(data.m1);
        m2Out.textContent = pretty(data.m2);
        m3Out.textContent = pretty(data.m3);
        m4Out.textContent = pretty(data.m4);
        m5Out.textContent = pretty(data.m5);
        m6Out.textContent = pretty(data.m6);
        ticketJson.value = pretty(data.m1);
        m1Badge.textContent = ["m2", "m5", "m6"].includes(data.mode) ? "Provided" : "Complete";
        m2Badge.textContent = ["m5", "m6"].includes(data.mode) ? "Via agent flow" : "Complete";
        m3Badge.textContent = ["m5", "m6"].includes(data.mode) ? "Via agent flow" : "Complete";
        m4Badge.textContent = ["m5", "m6"].includes(data.mode) ? "Via agent flow" : "Complete";
        m5Badge.textContent = data.m5?.interrupted ? "Waiting approval" : (data.mode === "m5" ? "Complete" : "Not run");
        m6Badge.textContent = data.mode === "m6" ? "Complete" : "Not run";
        m1Badge.className = "badge";
        m2Badge.className = "badge";
        m3Badge.className = "badge";
        m4Badge.className = "badge";
        m5Badge.className = data.m5?.interrupted ? "badge pending" : "badge";
        m6Badge.className = "badge";
        currentRunId = data.m5?.run_id || null;
        setResumeEnabled(Boolean(data.m5?.interrupted && currentRunId));
        setStatus(data.m5?.interrupted ? "M5 paused for human approval." : "Run complete.");
      } catch (err) {
        setStatus(String(err), true);
      }
    }

    async function resume(decision) {
      if (!currentRunId) return;
      setStatus("Resuming M5 workflow...");
      const res = await fetch("/api/resume", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({run_id: currentRunId, decision})
      });
      const data = await res.json();
      if (!res.ok) {
        setStatus(data.error || "Resume failed.", true);
        return;
      }
      m5Out.textContent = pretty(data.m5);
      m5Badge.textContent = "Complete";
      m5Badge.className = "badge";
      setResumeEnabled(false);
      setStatus("M5 resume complete.");
    }

    document.querySelector("#sampleBtn").addEventListener("click", () => loadSample("legal"));
    document.querySelector("#autoSampleBtn").addEventListener("click", () => loadSample("auto"));
    document.querySelector("#runBtn").addEventListener("click", run);
    document.querySelector("#approveBtn").addEventListener("click", () => resume({action: "approved", approved_by: "tester", note: "Approved from workbench"}));
    document.querySelector("#rejectBtn").addEventListener("click", () => resume({action: "rejected", approved_by: "tester", note: "Rejected from workbench"}));
    rawText.value = %DEFAULT_TEXT%;
    loadSample("legal");
  </script>
</body>
</html>
"""


def _sample_record() -> dict[str, Any]:
    path = PROJECT_ROOT / "data" / "shopsense" / "intake" / "records.jsonl"
    first = json.loads(path.read_text().splitlines()[0])
    return {
        "raw_text": first["raw_text"],
        "customer_ref": first["customer_ref"],
        "channel": first["channel"],
        "today": first["received_at"][:10],
        "ticket_json": {
            "issue_type": "refund_request",
            "order_ref": first["order_ref"],
            "sentiment": "angry",
            "urgency": "critical",
            "claimed_amount_inr": first["ground_truth"]["claimed_amount_inr"],
            "contact_number": 2,
            "escalation_signals": first["ground_truth"]["escalation_triggers"],
            "prompt_injection_suspected": False,
            "missing_fields": first["ground_truth"]["missing_fields"],
            "summary": "Customer demands a full refund for a late delivery and mentions legal action.",
        },
    }


def _auto_sample_record() -> dict[str, Any]:
    repo = get_repository()
    refunded = {r["order_ref"] for r in repo.rows("refunds") + repo.rows("replacements")}
    selected: dict[str, Any] | None = None
    for raw in repo.rows("orders"):
        order = lookups.get_order(repo, raw["customer_ref"], raw["order_ref"])
        customer = lookups.get_customer(repo, raw["customer_ref"])
        delivered = delivered_on(raw)
        if (
            order
            and raw["status"] == "delivered"
            and delivered is not None
            and raw["order_ref"] not in refunded
            and customer.get("automated_refunds_allowed") != "False"
            and customer.get("serial_refund_requester") != "True"
            and customer.get("flagged_for_abuse") != "True"
            and float(raw["order_value_inr"]) <= 2000
            and int(raw["actual_delivery_days"]) > int(raw["delivery_promise_days"])
            and delivered <= date(2026, 3, 10)
        ):
            selected = order
            break
    if not selected:
        raise RuntimeError("No low-risk late-delivery order found in seed data.")
    return {
        "raw_text": f"Please refund order {selected['order_ref']} because the delivery was late.",
        "customer_ref": selected["customer_ref"],
        "channel": "email",
        "today": "2026-03-10",
        "ticket_json": {
            "issue_type": "delivery_delay",
            "order_ref": selected["order_ref"],
            "sentiment": "calm",
            "urgency": "normal",
            "claimed_amount_inr": float(selected["order_value_inr"]),
            "contact_number": 1,
            "escalation_signals": [],
            "prompt_injection_suspected": False,
            "missing_fields": [],
            "summary": "Customer requests a refund because the delivery was late.",
        },
    }


def _client_from_ticket(ticket: SupportTicket) -> LLMClient:
    payload = ticket.model_dump(mode="json")

    def completion(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
        )

    return LLMClient(completion=completion)


def _workflow_view(result: dict[str, Any]) -> dict[str, Any]:
    if "__interrupt__" in result:
        interrupts = result["__interrupt__"]
        payloads = [getattr(item, "value", item) for item in interrupts]
        first = payloads[0] if payloads else {}
        return {
            "run_id": first.get("run_id"),
            "interrupted": True,
            "status": "paused_for_human",
            "route": "human_interrupt",
            "interrupt": first,
        }
    checkpoints = result.get("checkpoints", [])
    return {
        "run_id": result.get("run_id"),
        "interrupted": False,
        "status": result.get("status"),
        "route": result.get("route"),
        "final_message": result.get("final_message"),
        "ticket": result.get("ticket"),
        "memory_context": result.get("memory_context"),
        "policy_answer": result.get("policy_answer"),
        "action_proposal": result.get("action_proposal"),
        "human_decision": result.get("human_decision"),
        "checkpoint_count": len(checkpoints),
        "checkpoints": checkpoints,
    }


def _team_view(result) -> dict[str, Any]:
    return {
        "channel": result.channel,
        "customer_ref": result.customer_ref,
        "tool_transport": result.action_proposal.get("tool_result", {}).get("transport", "python"),
        "agents": [
            {"agent": step.agent, "summary": step.summary, "output": step.output}
            for step in result.steps
        ],
        "escalation_review": result.escalation_review,
        "action_proposal": result.action_proposal,
        "memory_context": result.memory_context,
        "policy_answer": result.policy_answer,
    }


def run_pipeline(payload: dict[str, Any], client: LLMClient | None = None,
                 repo: Repository | None = None,
                 memory_store: CustomerMemoryStore | None = None,
                 policy_index: PolicyIndex | None = None,
                 policy_agent: PolicyAgent | None = None) -> dict[str, Any]:
    mode = payload.get("mode", "full")
    customer_ref = str(payload.get("customer_ref") or "").strip()
    if not customer_ref:
        raise ValueError("customer_ref is required")
    today = date.fromisoformat(payload.get("today") or date.today().isoformat())

    if mode in {"m2", "m5", "m6"}:
        ticket_input = payload.get("ticket_json") or "{}"
        if isinstance(ticket_input, str):
            ticket = SupportTicket.model_validate_json(ticket_input)
        else:
            ticket = SupportTicket.model_validate(ticket_input)
    else:
        raw_text = str(payload.get("raw_text") or "").strip()
        if not raw_text:
            raise ValueError("raw_text is required")
        ticket = parse_ticket(
            client or LLMClient(),
            raw_text,
            channel=payload.get("channel"),
            auto_refund_cap_inr=2000,
            repeat_contact_threshold=3,
        )

    if mode == "m5":
        deps = WorkflowDeps(
            client=client or _client_from_ticket(ticket),
            repo=repo,
            memory_store=memory_store,
            policy_index=policy_index,
            policy_agent=policy_agent,
        )
        run_id = str(payload.get("run_id") or f"ui-{uuid4().hex[:10]}")
        result = run_ticket_workflow(
            raw_text=str(payload.get("raw_text") or ticket.summary),
            channel=str(payload.get("channel") or "email"),
            customer_ref=customer_ref,
            today=today.isoformat(),
            run_id=run_id,
            execute_actions=bool(payload.get("execute", False)),
            deps=deps,
        )
        m5 = _workflow_view(dict(result))
        workflow_ticket = m5.get("ticket") or ticket.model_dump(mode="json")
        return {
            "mode": mode,
            "m1": workflow_ticket,
            "m2": m5.get("action_proposal") or {},
            "m3": {"customer_context": m5.get("memory_context") or {}, "policy_hits": []},
            "m4": m5.get("policy_answer") or {},
            "m5": m5,
        }

    if mode == "m6":
        mcp_client = ShopSenseMCPClient(env={"CAPSTONE_RUNTIME_ROOT": str(PROJECT_ROOT / "runtime")})
        team = MultiAgentTeam(
            client=client or _client_from_ticket(ticket),
            repo=repo or get_repository(),
            memory_store=memory_store or get_memory_store(),
            policy_index=policy_index,
            policy_agent=policy_agent,
            tool_gateway=MCPShopSenseToolGateway(mcp_client),
        )
        team_result = team.resolve(
            raw_text=str(payload.get("raw_text") or ticket.summary),
            channel=str(payload.get("channel") or "email"),
            customer_ref=customer_ref,
            today=today.isoformat(),
            execute_actions=bool(payload.get("execute", False)),
        )
        m6 = _team_view(team_result)
        return {
            "mode": mode,
            "m1": team_result.ticket,
            "m2": team_result.action_proposal,
            "m3": {"customer_context": team_result.memory_context, "policy_hits": []},
            "m4": team_result.policy_answer,
            "m5": {"status": "not_run", "message": "Switch run mode to M5 workflow from JSON."},
            "m6": m6,
        }

    proposal = plan_action(
        repo or get_repository(),
        ticket,
        customer_ref=customer_ref,
        today=today,
        execute=bool(payload.get("execute", False)),
    )

    memory = memory_store or get_memory_store()
    memory.append_ticket(
        customer_ref,
        ticket,
        proposal,
        channel=payload.get("channel"),
        received_at=payload.get("today"),
    )
    context = memory.customer_context(customer_ref)

    index = policy_index or PolicyIndex.from_settings()
    if not index.client.collection_exists(index.collection_name):
        index.build(recreate=False)
    policy_query = " ".join([
        ticket.issue_type.value,
        ticket.summary,
        " ".join(signal.value for signal in ticket.escalation_signals),
        proposal.explanation,
    ])
    hits = [hit.model_dump(mode="json") for hit in index.search(policy_query, limit=3)]
    answer_agent = policy_agent or PolicyAgent(HybridPolicyRetriever(index))
    policy_answer = answer_agent.answer(policy_query)
    return {
        "mode": mode,
        "m1": ticket.model_dump(mode="json"),
        "m2": proposal.model_dump(mode="json"),
        "m3": {
            "customer_context": context,
            "policy_hits": hits,
        },
        "m4": policy_answer.model_dump(mode="json"),
        "m5": {"status": "not_run", "message": "Switch run mode to M5 workflow from JSON."},
        "m6": {"status": "not_run", "message": "Switch run mode to M6 multi-agent via MCP."},
    }


def resume_pipeline(payload: dict[str, Any]) -> dict[str, Any]:
    run_id = str(payload.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("run_id is required")
    decision = payload.get("decision")
    if not isinstance(decision, dict):
        raise ValueError("decision must be an object")
    result = resume_ticket_workflow(run_id=run_id, decision=decision)
    return {"m5": _workflow_view(dict(result))}


class WorkbenchHandler(BaseHTTPRequestHandler):
    server_version = "ShopSenseWorkbench/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            html = HTML.replace("%DEFAULT_TEXT%", json.dumps(DEFAULT_RAW_TEXT))
            self._send(HTTPStatus.OK, html, "text/html; charset=utf-8")
        elif path == "/api/sample":
            kind = parse_qs(parsed.query).get("kind", ["legal"])[0]
            sample = _auto_sample_record() if kind == "auto" else _sample_record()
            self._send_json(HTTPStatus.OK, sample)
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in {"/api/run", "/api/resume"}:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            body = resume_pipeline(payload) if path == "/api/resume" else run_pipeline(payload)
            self._send_json(HTTPStatus.OK, body)
        except ValidationError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"stage": "m2", "error": str(exc)})
        except Exception as exc:
            stage = "m1" if "LLM" in type(exc).__name__ or "API" in str(exc).upper() else "run"
            self._send_json(HTTPStatus.BAD_REQUEST, {"stage": stage, "error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _send_json(self, status: HTTPStatus, body: dict[str, Any]) -> None:
        self._send(status, json.dumps(body, indent=2), "application/json; charset=utf-8")

    def _send(self, status: HTTPStatus, body: str, content_type: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the ShopSense local milestone workbench.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()

    settings = get_settings()
    Path(settings.state_dir).mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), WorkbenchHandler)
    print(f"ShopSense workbench running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
