"""Offline support adapter with explicit fault boundaries and validated evidence."""
import asyncio
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.chaos.engine import FaultInjector
from app.runtime.retry import RecoverableStepError, run_with_retry
from app.schemas.chaos import ExecutionOptions
from app.schemas.trace import SpanType
from app.tracing.tracer import Tracer

ENDPOINT = 'builtin://support'
VERSION = '1.0.0'
RUNTIME_VERSION = 'support-runtime/3.0.0'
VERSIONS = {
    '1.0.0': {'refund_window_days': 30, 'default_attempts': 1, 'description': 'Baseline fixture adapter'},
    '1.1.0': {'refund_window_days': 30, 'default_attempts': 2, 'description': 'Resilient fixture adapter'},
    '1.1.0-regression': {'refund_window_days': 7, 'default_attempts': 2, 'description': 'Deliberately faulty fixture: uses a 7-day window'},
}
PROVENANCE = {'model': 'deterministic-template', 'prompt_version': 'support-answer-template/1.0.0',
              'tool_version': 'order-fixtures/2.0.0', 'retrieval_version': 'refund-policy-v1'}
ORDER_AGES = {'ORD-1001': 12, 'ORD-1002': 45, 'ORD-1003': 30, 'ORD-1004': 31}
POLICY = {'id': 'refund-policy-v1', 'text': 'Orders delivered within 30 days are eligible for a refund.'}


class SupportInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: str = Field(default='Can I refund my order?', min_length=1, max_length=2000)
    order_id: Literal['ORD-1001', 'ORD-1002', 'ORD-1003', 'ORD-1004'] = 'ORD-1001'
    scenario: Literal['success', 'tool_timeout'] = 'success'


async def execute(payload: dict, tracer: Tracer, options: ExecutionOptions | None = None, version: str = VERSION, playback=None) -> dict:
    options = options or ExecutionOptions()
    injector = FaultInjector(options.fault, tracer)
    with tracer.span('validate_input', SpanType.USER_INPUT) as span:
        request = SupportInput.model_validate(payload)
        span.output = request.model_dump()

    async def retrieve(attempt):
        with tracer.span('retrieve_refund_policy', SpanType.RETRIEVAL,
                         input={'query': request.question}, metadata={'attempt': attempt}) as span:
            if playback is not None:
                recorded = playback.consume('retrieve_refund_policy', {'query': request.question}, span)
                documents = recorded.get('documents', [])
                if POLICY not in documents:
                    raise RecoverableStepError('No recognized refund policy in retrieved evidence')
                return documents
            await asyncio.sleep(0.02)
            fault = injector.decide('retrieve_refund_policy', attempt)
            documents = [dict(POLICY)]
            if fault == 'missing_documents':
                documents = []
            elif fault == 'irrelevant_retrieval':
                documents = [{'id': 'shipping-policy-v1', 'text': 'Standard shipping takes five business days.'}]
            span.output = {'documents': documents}
            if POLICY not in documents:
                raise RecoverableStepError('No recognized refund policy in retrieved evidence')
            return documents

    async def lookup(attempt):
        with tracer.span('lookup_order', SpanType.TOOL_CALL,
                         input={'order_id': request.order_id},
                         metadata={'fixture': True, 'attempt': attempt}) as span:
            if playback is not None:
                order = playback.consume('lookup_order', {'order_id': request.order_id}, span)
                if type(order.get('days_since_delivery')) is not int or order['days_since_delivery'] < 0:
                    raise RecoverableStepError('Order API returned invalid days_since_delivery')
                return order
            await asyncio.sleep(0.03)
            fault = injector.decide('lookup_order', attempt)
            if fault == 'tool_timeout' or request.scenario == 'tool_timeout':
                raise TimeoutError('Simulated order API timeout')
            order = {'order_id': request.order_id,
                     'days_since_delivery': ORDER_AGES[request.order_id]}
            if fault == 'malformed_tool':
                order = {'order_id': request.order_id, 'days_since_delivery': 'not-a-number'}
            span.output = order
            if type(order.get('days_since_delivery')) is not int or order['days_since_delivery'] < 0:
                raise RecoverableStepError('Order API returned invalid days_since_delivery')
            return order

    with tracer.span('resolve_refund_request', SpanType.PLANNER,
                     metadata={'mode': 'offline', 'adapter_version': version, 'runtime_version': RUNTIME_VERSION}):
        documents = await run_with_retry(retrieve, options.retry, tracer, 'retrieve_refund_policy')
        order = await run_with_retry(lookup, options.retry, tracer, 'lookup_order')
        with tracer.span('compose_answer', SpanType.MODEL,
                         metadata={'simulated': True, 'model': 'deterministic-template'},
                         input={'order': order, 'documents': documents}) as span:
            await asyncio.sleep(0.01)
            eligible = order['days_since_delivery'] <= VERSIONS[version]['refund_window_days']
            answer = {'answer': f"Order {request.order_id} is {'eligible' if eligible else 'not eligible'} for a refund under the 30-day policy [refund-policy-v1].",
                      'citations': [POLICY['id']], 'eligible': eligible}
            span.output = answer
        with tracer.span('final_response', SpanType.FINAL_RESPONSE) as span:
            span.output = answer
        return answer
