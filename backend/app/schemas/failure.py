"""Failure Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FailureSeverity(str, Enum):
    """Severity level of a detected failure."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FailureCategory(str, Enum):
    """Category classifying the kind of failure observed."""

    WRONG_TOOL = "wrong_tool"                  # Agent called an incorrect or forbidden tool
    MISSING_TOOL = "missing_tool"              # Agent failed to invoke an expected tool
    HALLUCINATION = "hallucination"            # Agent generated unsupported claims
    WRONG_ANSWER = "wrong_answer"              # Final response is factually incorrect
    POLICY_VIOLATION = "policy_violation"      # Agent violated a defined policy rule
    RETRIEVAL_FAILURE = "retrieval_failure"    # Relevant documents not retrieved
    LATENCY_BREACH = "latency_breach"          # SLA latency exceeded
    TOOL_ERROR = "tool_error"                  # Tool execution produced an error
    LOOP_DETECTED = "loop_detected"            # Agent entered a repetitive loop
    CONTEXT_OVERFLOW = "context_overflow"      # Token/context limit breached
    UNKNOWN = "unknown"                        # Unclassified failure


class FailureBase(BaseModel):
    """Shared failure fields."""

    run_id: uuid.UUID = Field(..., description="Run in which this failure was detected.")
    category: FailureCategory = Field(..., description="Failure category.")
    severity: FailureSeverity = Field(..., description="Severity level.")
    title: str = Field(..., min_length=1, max_length=512, description="Short failure title.")
    description: str | None = Field(default=None, description="Detailed failure description.")
    evidence: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw evidence supporting the failure classification (span excerpts, diffs, etc.).",
    )
    suspected_component: str | None = Field(
        default=None,
        description="Which component of the agent is suspected to have caused this failure.",
    )


class FailureCreate(FailureBase):
    """Request body for recording a detected failure."""

    pass


class FailureResponse(FailureBase):
    """Failure representation returned by the API."""

    id: uuid.UUID = Field(..., description="Unique failure identifier.")
    created_at: datetime = Field(..., description="UTC timestamp of failure detection.")

    model_config = ConfigDict(from_attributes=True)
