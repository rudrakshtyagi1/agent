"""Versioned deterministic evaluation expectations stored in test metadata."""
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class EvaluationExpectations(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_output: dict[str, Any] = Field(default_factory=dict)
    max_latency_ms: float | None = Field(default=None, gt=0, allow_inf_nan=False)


def snapshot_case(case) -> dict:
    return {"name": case.name, "input": case.input,
            "expected_tools": case.expected_tools, "forbidden_tools": case.forbidden_tools,
            "expected_documents": case.expected_documents,
            "expected_behavior": case.expected_behavior, "metadata": case.tc_metadata}
