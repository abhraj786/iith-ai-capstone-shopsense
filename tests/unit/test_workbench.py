"""Workbench tests use fake M1 output, so they do not call a model."""

import json
from types import SimpleNamespace

from capstone.llm.client import LLMClient
from capstone.settings import Settings, get_settings
from capstone.tools.repository import Repository
from capstone.workbench.app import run_pipeline


def test_workbench_runs_m1_and_m2_with_fake_llm(tmp_path):
    output = {
        "issue_type": "refund_request",
        "order_ref": "KW-O-000950",
        "sentiment": "angry",
        "urgency": "critical",
        "claimed_amount_inr": 6499,
        "contact_number": 2,
        "escalation_signals": ["angry_or_abusive", "legal_or_regulatory"],
        "prompt_injection_suspected": False,
        "missing_fields": [],
        "summary": "Customer demands a refund and mentions legal action.",
    }

    def completion(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(output)))]
        )

    result = run_pipeline(
        {
            "mode": "full",
            "raw_text": "Refund 6,499 INR for order KW-O-000950 or I will file a legal complaint.",
            "channel": "email",
            "customer_ref": "KW-C-00285",
            "today": "2026-03-10",
        },
        client=LLMClient(Settings(llm_max_retries=0), completion=completion),
        repo=Repository(get_settings().seed_dir, tmp_path / "state"),
    )

    assert result["m1"]["order_ref"] == "KW-O-000950"
    assert result["m2"]["recommended_action"] == "human_review"
    assert result["m2"]["tool_args"]["trigger"] == "legal_or_regulatory"
