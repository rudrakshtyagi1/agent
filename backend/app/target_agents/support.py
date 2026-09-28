"""Deterministic, offline support-agent adapter; no external side effects."""
import asyncio
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.trace import SpanType
from app.tracing.tracer import Tracer

ENDPOINT = "builtin://support"
VERSION = "1.0.0"


class SupportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(default="Can I refund my order?", min_length=1, max_length=2000)
    order_id: Literal["ORD-1001", "ORD-1002"] = "ORD-1001"
    scenario: Literal["success", "tool_timeout"] = "success"


async def execute(payload: dict, tracer: Tracer) -> dict:
    with tracer.span("validate_input", SpanType.USER_INPUT) as span:
        request = SupportInput.model_validate(payload)
        span.output = request.model_dump()
    with tracer.span("resolve_refund_request", SpanType.PLANNER,
                     metadata={"mode": "offline", "adapter_version": VERSION}):
        with tracer.span("retrieve_refund_policy", SpanType.RETRIEVAL,
                         input={"query": request.question}) as span:
            await asyncio.sleep(0.02)
            policy = {"id": "refund-policy-v1", "text": "Orders delivered within 30 days are eligible for a refund."}
            span.output = {"documents": [policy]}
        with tracer.span("lookup_order", SpanType.TOOL_CALL,
                         input={"order_id": request.order_id},
                         metadata={"fixture": True}) as span:
            await asyncio.sleep(0.03)
            if request.scenario == "tool_timeout":
                raise TimeoutError("Simulated order API timeout")
            order = {"order_id": request.order_id,
                     "days_since_delivery": 12 if request.order_id == "ORD-1001" else 45}
            span.output = order
        with tracer.span("compose_answer", SpanType.MODEL,
                         metadata={"simulated": True, "model": "deterministic-template"},
                         input={"order": order, "documents": [policy]}) as span:
            await asyncio.sleep(0.01)
            eligible = order["days_since_delivery"] <= 30
            answer = {"answer": f"Order {request.order_id} is {'eligible' if eligible else 'not eligible'} for a refund under the 30-day policy [refund-policy-v1].",
                      "citations": [policy["id"]], "eligible": eligible}
            span.output = answer
        with tracer.span("final_response", SpanType.FINAL_RESPONSE) as span:
            span.output = answer
        return answer
