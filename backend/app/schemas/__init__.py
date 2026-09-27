"""AgentGuard Pydantic schema exports."""

from app.schemas.agent import AgentCreate, AgentResponse, AgentStatus, AgentUpdate
from app.schemas.evaluation import (
    EvaluationCreate,
    EvaluationDimension,
    EvaluationResponse,
)
from app.schemas.failure import (
    FailureCategory,
    FailureCreate,
    FailureResponse,
    FailureSeverity,
)
from app.schemas.run import RunCreate, RunResponse, RunStatus, RunUpdate
from app.schemas.test_case import (
    TestCaseCategory,
    TestCaseCreate,
    TestCaseResponse,
    TestCaseUpdate,
)
from app.schemas.trace import SpanCreate, SpanResponse, SpanType, TraceResponse

__all__ = [
    # Agent
    "AgentStatus",
    "AgentCreate",
    "AgentUpdate",
    "AgentResponse",
    # TestCase
    "TestCaseCategory",
    "TestCaseCreate",
    "TestCaseUpdate",
    "TestCaseResponse",
    # Run
    "RunStatus",
    "RunCreate",
    "RunUpdate",
    "RunResponse",
    # Trace / Span
    "SpanType",
    "SpanCreate",
    "SpanResponse",
    "TraceResponse",
    # Evaluation
    "EvaluationDimension",
    "EvaluationCreate",
    "EvaluationResponse",
    # Failure
    "FailureSeverity",
    "FailureCategory",
    "FailureCreate",
    "FailureResponse",
]
