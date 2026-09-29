"""Bounded comparison and release-gate contracts for registered fixture versions."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

AgentVersion = Literal['1.0.0', '1.1.0', '1.1.0-regression']


class GatePolicy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    max_regressions: int = Field(default=0, ge=0, le=100, strict=True)
    min_task_success_rate: float = Field(default=1, ge=0, le=1, allow_inf_nan=False)
    min_measured_cases: int = Field(default=5, ge=1, le=100, strict=True)
    max_mean_latency_increase_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class ComparisonRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    baseline_version: AgentVersion = '1.0.0'
    candidate_version: AgentVersion = '1.1.0'
    gate: GatePolicy = Field(default_factory=GatePolicy)


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    candidate_version: AgentVersion = '1.1.0'
