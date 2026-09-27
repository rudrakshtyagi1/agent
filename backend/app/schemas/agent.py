"""Agent Pydantic schemas for API layer."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentStatus(str, Enum):
    """Lifecycle status of a registered agent."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"


class AgentBase(BaseModel):
    """Shared fields used for creation and response."""

    name: str = Field(..., min_length=1, max_length=256, description="Human-readable agent name.")
    version: str = Field(..., min_length=1, max_length=64, description="Semantic or arbitrary version string.")
    description: str | None = Field(default=None, description="Optional agent description.")
    endpoint: str | None = Field(default=None, description="Optional HTTP endpoint or identifier of the agent.")
    model: str | None = Field(default=None, description="Underlying LLM model name/identifier.")
    status: AgentStatus = Field(default=AgentStatus.ACTIVE, description="Agent operational status.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary agent metadata for future use.")


class AgentCreate(AgentBase):
    """Request body for registering a new agent."""

    pass


class AgentUpdate(BaseModel):
    """Partial update request for an existing agent."""

    name: str | None = Field(default=None, min_length=1, max_length=256)
    version: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = None
    endpoint: str | None = None
    model: str | None = None
    status: AgentStatus | None = None
    metadata: dict[str, Any] | None = None


class AgentResponse(AgentBase):
    """Agent representation returned by the API."""

    id: uuid.UUID = Field(..., description="Unique agent identifier.")
    created_at: datetime = Field(..., description="UTC timestamp of registration.")

    model_config = ConfigDict(from_attributes=True)
