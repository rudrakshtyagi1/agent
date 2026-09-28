"""Retry only explicitly recoverable fixture failures; cancellation propagates."""
import asyncio
from app.schemas.chaos import RetryPolicy
from app.schemas.trace import SpanType


class RecoverableStepError(Exception):
    """Invalid tool results or insufficient retrieved evidence."""


async def run_with_retry(operation, policy: RetryPolicy, tracer, target: str):
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await operation(attempt)
        except (TimeoutError, RecoverableStepError) as exc:
            if attempt == policy.max_attempts:
                raise
            # Linear backoff; at most two sleeps, each capped at 400 ms.
            delay_ms = policy.backoff_ms * attempt
            with tracer.span('retry_scheduled', SpanType.STATE_TRANSITION) as event:
                event.output = {'target': target, 'failed_attempt': attempt,
                                'next_attempt': attempt + 1, 'delay_ms': delay_ms,
                                'reason': f'{type(exc).__name__}: {exc}'}
            await asyncio.sleep(delay_ms / 1000)
