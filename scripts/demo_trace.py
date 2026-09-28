"""Run from the repo root: PYTHONPATH=backend python3 scripts/demo_trace.py."""

from uuid import uuid4

from app.schemas.trace import SpanType
from app.tracing.tracer import Tracer


def main():
    tracer = Tracer(uuid4())
    try:
        with tracer.span("support_agent", SpanType.PLANNER):
            with tracer.span("retrieve_policy", SpanType.RETRIEVAL) as retrieval:
                retrieval.output = {"document_ids": ["refund-policy-v1"]}
            with tracer.span("lookup_order", SpanType.TOOL_CALL):
                raise TimeoutError("Simulated order API timeout")
    except TimeoutError:
        pass  # Demo intentionally fails; the trace retains the failure.
    print(tracer.snapshot().model_dump_json(indent=2))


if __name__ == "__main__":
    main()
