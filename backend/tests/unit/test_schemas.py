"""Unit tests — Pydantic schema validation."""

import uuid
import pytest
from datetime import datetime, timezone

from app.schemas.agent import AgentCreate, AgentResponse, AgentStatus
from app.schemas.test_case import TestCaseCreate, TestCaseCategory
from app.schemas.run import RunCreate, RunStatus
from app.schemas.trace import SpanType, SpanCreate
from app.schemas.evaluation import EvaluationCreate, EvaluationDimension
from app.schemas.failure import FailureCreate, FailureCategory, FailureSeverity


# ------------------------------------------------------------------ #
# Agent schemas
# ------------------------------------------------------------------ #

def test_agent_create_minimal():
    agent = AgentCreate(name="test-agent", version="1.0.0")
    assert agent.name == "test-agent"
    assert agent.version == "1.0.0"
    assert agent.status == AgentStatus.ACTIVE
    assert agent.metadata == {}


def test_agent_create_full():
    agent = AgentCreate(
        name="support-agent",
        version="2.1.0",
        description="Customer support agent",
        endpoint="http://localhost:9000",
        model="llama3.2",
        status=AgentStatus.ACTIVE,
        metadata={"team": "cx"},
    )
    assert agent.description == "Customer support agent"
    assert agent.model == "llama3.2"


def test_agent_status_enum_values():
    assert AgentStatus.ACTIVE.value == "active"
    assert AgentStatus.INACTIVE.value == "inactive"
    assert AgentStatus.DEPRECATED.value == "deprecated"


def test_agent_create_name_required():
    with pytest.raises(Exception):
        AgentCreate(version="1.0")


def test_agent_create_version_required():
    with pytest.raises(Exception):
        AgentCreate(name="agent")


# ------------------------------------------------------------------ #
# TestCase schemas
# ------------------------------------------------------------------ #

def test_test_case_create_minimal():
    tc = TestCaseCreate(name="cancel order test")
    assert tc.category == TestCaseCategory.FUNCTIONAL
    assert tc.input == {}
    assert tc.expected_tools == []
    assert tc.forbidden_tools == []
    assert tc.tags == []


def test_test_case_create_full():
    tc = TestCaseCreate(
        name="refund flow golden",
        category=TestCaseCategory.GOLDEN,
        input={"message": "I want a refund"},
        expected_tools=["refund_order"],
        forbidden_tools=["cancel_order"],
        expected_behavior="Agent should initiate refund",
        tags=["refund", "golden"],
    )
    assert tc.category == TestCaseCategory.GOLDEN
    assert "refund_order" in tc.expected_tools
    assert "refund" in tc.tags


def test_test_case_category_enum_values():
    assert TestCaseCategory.GOLDEN.value == "golden"
    assert TestCaseCategory.ADVERSARIAL.value == "adversarial"
    assert TestCaseCategory.REGRESSION.value == "regression"
    assert TestCaseCategory.CHAOS.value == "chaos"
    assert TestCaseCategory.FUNCTIONAL.value == "functional"


# ------------------------------------------------------------------ #
# Run schemas
# ------------------------------------------------------------------ #

def test_run_create_valid():
    agent_id = uuid.uuid4()
    tc_id = uuid.uuid4()
    run = RunCreate(agent_id=agent_id, agent_version="1.0.0", test_case_id=tc_id)
    assert run.agent_id == agent_id
    assert run.agent_version == "1.0.0"
    assert run.test_case_id == tc_id


def test_run_status_enum():
    assert RunStatus.QUEUED.value == "queued"
    assert RunStatus.RUNNING.value == "running"
    assert RunStatus.COMPLETED.value == "completed"
    assert RunStatus.FAILED.value == "failed"


# ------------------------------------------------------------------ #
# Span / Trace schemas
# ------------------------------------------------------------------ #

def test_span_type_enum_completeness():
    expected = {
        "user_input", "planner", "retrieval", "reranker", "model",
        "tool_call", "tool_result", "state_transition", "final_response", "error",
    }
    actual = {t.value for t in SpanType}
    assert actual == expected


def test_span_create_valid():
    run_id = uuid.uuid4()
    trace_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    span = SpanCreate(
        trace_id=trace_id,
        run_id=run_id,
        span_type=SpanType.TOOL_CALL,
        name="call_refund_order",
        started_at=now,
    )
    assert span.span_type == SpanType.TOOL_CALL
    assert span.parent_span_id is None


# ------------------------------------------------------------------ #
# Evaluation schemas
# ------------------------------------------------------------------ #

def test_evaluation_create():
    run_id = uuid.uuid4()
    ev = EvaluationCreate(
        run_id=run_id,
        evaluator="tool_correctness",
        dimension=EvaluationDimension.DETERMINISTIC,
        score=0.9,
        passed=True,
    )
    assert ev.dimension == EvaluationDimension.DETERMINISTIC
    assert ev.score == 0.9


def test_evaluation_score_bounds():
    run_id = uuid.uuid4()
    with pytest.raises(Exception):
        EvaluationCreate(
            run_id=run_id,
            evaluator="x",
            dimension=EvaluationDimension.SEMANTIC,
            score=1.5,  # out of bounds
        )


# ------------------------------------------------------------------ #
# Failure schemas
# ------------------------------------------------------------------ #

def test_failure_create():
    run_id = uuid.uuid4()
    f = FailureCreate(
        run_id=run_id,
        category=FailureCategory.WRONG_TOOL,
        severity=FailureSeverity.HIGH,
        title="Called forbidden tool",
    )
    assert f.severity == FailureSeverity.HIGH
    assert f.evidence == {}


def test_failure_severity_values():
    assert FailureSeverity.LOW.value == "low"
    assert FailureSeverity.CRITICAL.value == "critical"
