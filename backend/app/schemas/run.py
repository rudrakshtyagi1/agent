"""Run Pydantic schemas for API layer.

A Run represents one complete execution of an Agent against a TestCase.
Every Run preserves the agent_version snapshot so historical runs remain
attributable regardless of subsequent agent updates.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunStatus(str, Enum):
    """Lifecycle states of a test run."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunBase(BaseModel):
    """Core run fields shared across request and response shapes."""

    agent_id: uuid.UUID = Field(..., description="Agent being tested.")
    # agent_version is snapshotted from the Agent at run creation time.
    # It is stored denormalised on the Run so historical data remains intact
    # even if the parent Agent record is updated or replaced.
    agent_version: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description=(
            "Exact agent version string at the moment the run was created. "
            "Denormalised to preserve traceability for future replay and regression comparison."
        ),
    )
    test_case_id: uuid.UUID = Field(..., description="Test case executed in this run.")


class RunCreate(RunBase):
    """Request body for creating a new run record.

    At Phase 1, POST /runs only persists a QUEUED record.
    Actual agent execution is deferred to a later phase.
    """

    pass


class RunUpdate(BaseModel):
    """Internal-use partial update for run lifecycle transitions."""

    status: RunStatus | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_latency_ms: int | None = None
    error: str | None = None


class RunResponse(RunBase):
    """Run representation returned by the API."""

    id: uuid.UUID = Field(..., description="Unique run identifier.")
    status: RunStatus = Field(..., description="Current lifecycle state of the run.")
    started_at: datetime | None = Field(default=None, description="When execution began (null if queued).")
    completed_at: datetime | None = Field(default=None, description="When execution finished (null if ongoing).")
    total_latency_ms: int | None = Field(default=None, description="End-to-end latency in milliseconds.")
    error: str | None = Field(default=None, description="Error message if the run failed.")
    created_at: datetime = Field(..., description="UTC timestamp when the run record was created.")

    model_config = ConfigDict(from_attributes=True)
