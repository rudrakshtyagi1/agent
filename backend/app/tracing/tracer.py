"""In-process tracing for one agent run, with task-local span ancestry.

Create one Tracer per run. Use ordinary ``with`` blocks in sync or async
functions; child asyncio tasks inherit their parent's active span.
Snapshots are in-memory only and should be exported after all tasks finish.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from time import perf_counter_ns
from uuid import UUID, uuid4

from app.schemas.trace import SpanResponse, SpanType, TraceResponse


class Tracer:
    def __init__(self, run_id: UUID):
        self.run_id = run_id
        self.trace_id = uuid4()
        self._spans: list[SpanResponse] = []
        self._parent: ContextVar[UUID | None] = ContextVar(
            f"agentguard_parent_{self.trace_id}", default=None
        )

    @contextmanager
    def span(self, name: str, span_type: SpanType, *, input=None, metadata=None):
        """Record timing and exceptions without swallowing agent failures.

        Set ``span.output`` before leaving the block to record its result.
        Inputs and outputs must be JSON-serializable for JSON export. Payloads
        are opt-in; callers must redact sensitive values before recording.
        """
        record = SpanResponse(
            id=uuid4(), trace_id=self.trace_id, run_id=self.run_id,
            parent_span_id=self._parent.get(), name=name, span_type=span_type,
            started_at=datetime.now(timezone.utc), input=input,
            metadata=metadata or {},
        )
        self._spans.append(record)
        token = self._parent.set(record.id)
        started = perf_counter_ns()
        try:
            yield record
        except BaseException as exc:
            # Includes asyncio cancellation; preserve the original exception.
            record.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            record.duration_ms = max(0, (perf_counter_ns() - started) // 1_000_000)
            record.ended_at = datetime.now(timezone.utc)
            self._parent.reset(token)

    def snapshot(self) -> TraceResponse:
        """Return an independent snapshot, including any still-active spans."""
        return TraceResponse(
            trace_id=self.trace_id, run_id=self.run_id,
            spans=[span.model_copy(deep=True) for span in self._spans],
        )
