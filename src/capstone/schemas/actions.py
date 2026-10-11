"""Typed action proposals for M2."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RecommendedAction(str, Enum):
    track_order = "track_order"
    refund = "refund"
    replacement = "replacement"
    human_review = "human_review"
    request_missing_info = "request_missing_info"
    no_action = "no_action"


class ActionProposal(BaseModel):
    recommended_action: RecommendedAction
    requires_human: bool = False
    reason_code: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    explanation: str
    executed: bool = False
    tool_result: dict[str, Any] | None = None
    tool_error: dict[str, str] | None = None
