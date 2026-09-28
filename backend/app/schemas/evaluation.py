"""EvaluationResult Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvaluationDimension(str, Enum):
    """High-level dimension an evaluator measures."""

    DETERMINISTIC = "deterministic"   # Rule-based correctness checks
    RETRIEVAL = "retrieval"           # Recall, MRR, NDCG metrics
    SEMANTIC = "semantic"             # Groundedness, hallucination, answer quality
    SYSTEM = "system"                 # Latency, efficiency, reliability


class EvaluationBase(BaseModel):
    """Shared evaluation fields."""

    run_id: uuid.UUID = Field(..., description="Run this evaluation belongs to.")
    evaluator: str = Field(..., min_length=1, max_length=256, description="Identifier for the evaluator.")
    dimension: EvaluationDimension = Field(..., description="Evaluation dimension.")
    score: float | None = Field(default=None, ge=0.0, le=1.0, description="Normalised score 0.0–1.0.")
    passed: bool | None = Field(default=None, description="Binary pass/fail result.")
    details: dict[str, Any] = Field(default_factory=dict, description="Evaluator-specific detail payload.")


class EvaluationCreate(EvaluationBase):
    """Request body for recording an evaluation result."""

    pass


class EvaluationResponse(EvaluationBase):
    """EvaluationResult representation returned by the API."""

    id: uuid.UUID = Field(..., description="Unique evaluation identifier.")
    created_at: datetime = Field(..., description="UTC timestamp of evaluation.")

    @field_validator("created_at")
    @classmethod
    def normalize_utc(cls, value):
        # SQLite drops timezone information; all persisted timestamps are UTC.
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    model_config = ConfigDict(from_attributes=True)
