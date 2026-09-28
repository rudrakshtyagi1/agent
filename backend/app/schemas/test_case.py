"""TestCase Pydantic schemas for API layer."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TestCaseCategory(str, Enum):
    """Semantic category classifying the test case intent."""

    __test__ = False  # Prevent pytest from treating this enum as a test suite

    GOLDEN = "golden"               # Known-good reference inputs/outputs
    ADVERSARIAL = "adversarial"     # Inputs designed to probe failure modes
    REGRESSION = "regression"       # Guard against previously fixed regressions
    CHAOS = "chaos"                 # Fault-injection / resilience testing
    FUNCTIONAL = "functional"       # Standard functional correctness tests


class TestCaseBase(BaseModel):
    """Shared TestCase fields."""

    __test__ = False  # Prevent pytest from treating this model as a test suite

    name: str = Field(..., min_length=1, max_length=512, description="Short descriptive name for the test case.")
    description: str | None = Field(default=None, description="What this test case exercises.")
    category: TestCaseCategory = Field(
        default=TestCaseCategory.FUNCTIONAL, description="Semantic category of the test."
    )
    # The agent input payload — arbitrary JSON-compatible dict.
    input: dict[str, Any] = Field(
        default_factory=dict,
        description="Input payload delivered to the agent under test.",
    )
    # Observability expectations — evaluated against the execution trace.
    expected_tools: list[str] = Field(
        default_factory=list,
        description="Tool names the agent is expected to invoke during this test.",
    )
    forbidden_tools: list[str] = Field(
        default_factory=list,
        description="Tool names the agent must NOT invoke during this test.",
    )
    expected_documents: list[str] = Field(
        default_factory=list,
        description="Document IDs or titles expected to be retrieved.",
    )
    expected_behavior: str | None = Field(
        default=None,
        description="Natural-language description of expected agent behaviour for LLM evaluators.",
    )
    tags: list[str] = Field(default_factory=list, description="Free-form tags for filtering and grouping.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata for future use.")


class TestCaseCreate(TestCaseBase):
    """Request body for creating a new test case."""

    __test__ = False

    @field_validator("metadata")
    @classmethod
    def validate_evaluation(cls, value):
        from app.evaluation.contracts import EvaluationExpectations
        if "evaluation" in value:
            EvaluationExpectations.model_validate(value["evaluation"])
        return value


class TestCaseUpdate(BaseModel):
    """Partial update request for an existing test case."""

    __test__ = False

    name: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = None
    category: TestCaseCategory | None = None
    input: dict[str, Any] | None = None
    expected_tools: list[str] | None = None
    forbidden_tools: list[str] | None = None
    expected_documents: list[str] | None = None
    expected_behavior: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class TestCaseResponse(TestCaseBase):
    """TestCase representation returned by the API."""

    __test__ = False

    id: uuid.UUID = Field(..., description="Unique test-case identifier.")
    created_at: datetime = Field(..., description="UTC timestamp of creation.")

    model_config = ConfigDict(from_attributes=True)
