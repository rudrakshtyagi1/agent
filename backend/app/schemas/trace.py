"""Trace and Span Pydantic schemas.

A Trace represents one complete agent execution session (1:1 with a Run).
Spans are the ordered/nested atomic events within a trace, supporting
full execution trajectory observability in later phases.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SpanType(str, Enum):
    """Semantic type of an execution span.

    These types map to the future evaluation dimensions:
    - USER_INPUT      : The raw input delivered to the agent.
    - PLANNER         : Planning / reasoning step.
    - RETRIEVAL       : Vector / keyword document retrieval.
    - RERANKER        : Re-ranking step on retrieved documents.
    - MODEL           : Direct LLM inference call.
    - TOOL_CALL       : Outbound tool/function invocation.
    - TOOL_RESULT     : Response received from a tool.
    - STATE_TRANSITION: Agent internal state change.
    - FINAL_RESPONSE  : Agent's completed output to the user.
    - ERROR           : An error event captured during execution.
    """

    USER_INPUT = "user_input"
    PLANNER = "planner"
    RETRIEVAL = "retrieval"
    RERANKER = "reranker"
    MODEL = "model"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    STATE_TRANSITION = "state_transition"
    FINAL_RESPONSE = "final_response"
    ERROR = "error"


class SpanBase(BaseModel):
    """Core span fields."""

    trace_id: uuid.UUID = Field(..., description="Identifier grouping all spans for one agent execution.")
    parent_span_id: uuid.UUID | None = Field(
        default=None, description="Parent span for nested / hierarchical traces."
    )
    run_id: uuid.UUID = Field(..., description="Run this span belongs to.")
    span_type: SpanType = Field(..., description="Semantic type of this execution span.")
    name: str = Field(..., min_length=1, max_length=256, description="Human-readable span name.")
    started_at: datetime = Field(..., description="When this span started.")
    ended_at: datetime | None = Field(default=None, description="When this span completed.")
    duration_ms: int | None = Field(default=None, ge=0, description="Duration in milliseconds.")
    input: dict[str, Any] | None = Field(default=None, description="Serialised span input data.")
    output: dict[str, Any] | None = Field(default=None, description="Serialised span output data.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Span-level metadata.")
    error: str | None = Field(default=None, description="Error detail if this span errored.")


class SpanCreate(SpanBase):
    """Request body for recording a new span."""

    pass


class SpanResponse(SpanBase):
    """Span representation returned by the API."""

    id: uuid.UUID = Field(..., description="Unique span identifier.")

    model_config = ConfigDict(from_attributes=True)


class TraceResponse(BaseModel):
    """Aggregated trace with all its spans, returned by the API."""

    trace_id: uuid.UUID = Field(..., description="Unique trace identifier.")
    run_id: uuid.UUID = Field(..., description="Run this trace belongs to.")
    spans: list[SpanResponse] = Field(default_factory=list, description="All spans in chronological order.")

    model_config = ConfigDict(from_attributes=True)
