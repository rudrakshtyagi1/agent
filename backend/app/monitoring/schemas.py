"""Bounded complete-trace ingestion contract."""

from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.trace import SpanType


class IncomingSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    parent_span_id: UUID | None = None
    name: str = Field(min_length=1, max_length=128)
    span_type: SpanType
    started_at: datetime
    ended_at: datetime
    error: str | None = Field(default=None, max_length=2000)
    input: dict | None = None
    output: dict | None = None
    metadata: dict = Field(default_factory=dict)
    input_tokens: int | None = Field(default=None, ge=0, le=100000000, strict=True)
    output_tokens: int | None = Field(default=None, ge=0, le=100000000, strict=True)

    @model_validator(mode="after")
    def timestamps(self):
        if not self.started_at.tzinfo or not self.ended_at.tzinfo:
            raise ValueError("Timestamps require timezone offsets")
        if self.ended_at < self.started_at:
            raise ValueError("Span ends before it starts")
        return self


class IncomingTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace_id: UUID
    agent_name: str = Field(min_length=1, max_length=128)
    agent_version: str = Field(min_length=1, max_length=64)
    environment: Literal["development", "staging", "production"] = "development"
    status: Literal["completed", "failed"]
    spans: list[IncomingSpan] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def tree(self):
        nodes = {s.id: s for s in self.spans}
        roots = [s for s in self.spans if s.parent_span_id is None]
        if len(nodes) != len(self.spans) or len(roots) != 1:
            raise ValueError("Trace requires unique span IDs and exactly one root")
        for span in self.spans:
            seen = {span.id}
            parent = span.parent_span_id
            while parent:
                if parent not in nodes or parent in seen:
                    raise ValueError("Invalid parent reference or cycle")
                seen.add(parent)
                parent = nodes[parent].parent_span_id
            if span.parent_span_id:
                p = nodes[span.parent_span_id]
                if span.started_at < p.started_at or span.ended_at > p.ended_at:
                    raise ValueError("Child timing must fit inside its parent")
        return self
