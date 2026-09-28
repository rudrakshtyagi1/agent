"""Strict, bounded local fault injection contracts."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

FaultKind = Literal['tool_timeout', 'malformed_tool', 'missing_documents', 'irrelevant_retrieval']
FAULT_KINDS = ['tool_timeout', 'malformed_tool', 'missing_documents', 'irrelevant_retrieval']


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    max_attempts: int = Field(default=1, ge=1, le=3, strict=True)
    backoff_ms: int = Field(default=20, ge=0, le=200, strict=True)


class FaultConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: FaultKind
    seed: int = Field(default=42, ge=0, le=2**32-1, strict=True)
    probability: float = Field(default=1, ge=0, le=1, allow_inf_nan=False)
    fail_first_attempts: int = Field(default=1, ge=1, le=3, strict=True)


class ExecutionOptions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fault: FaultConfig | None = None
    retry: RetryPolicy = Field(default_factory=RetryPolicy)


class CampaignRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    seed: int = Field(default=42, ge=0, le=2**32-1, strict=True)
    probability: float = Field(default=1, ge=0, le=1, allow_inf_nan=False)
    fail_first_attempts: int = Field(default=1, ge=1, le=3, strict=True)
    retry: RetryPolicy = Field(default_factory=lambda: RetryPolicy(max_attempts=2))
    order_id: Literal['ORD-1001', 'ORD-1002'] = 'ORD-1001'
    faults: list[FaultKind] = Field(default_factory=lambda: list(FAULT_KINDS), min_length=1, max_length=4)

    @field_validator('faults')
    @classmethod
    def unique_faults(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('Fault kinds must be unique')
        return value
