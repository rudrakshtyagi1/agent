"""Per-run deterministic fault decisions; no global RNG or external effects."""
import hashlib
from app.schemas.chaos import FaultConfig
from app.schemas.trace import SpanType

ENGINE_VERSION = 'agentguard-chaos/1.0.0'
TARGETS = {'tool_timeout': 'lookup_order', 'malformed_tool': 'lookup_order',
           'missing_documents': 'retrieve_refund_policy', 'irrelevant_retrieval': 'retrieve_refund_policy'}


class FaultInjector:
    def __init__(self, config: FaultConfig | None, tracer):
        self.config = config
        self.tracer = tracer

    def decide(self, target: str, attempt: int) -> str | None:
        config = self.config
        if config is None or TARGETS[config.kind] != target:
            return None
        key = f'{ENGINE_VERSION}:{config.seed}:{config.kind}:{target}:{attempt}'
        draw = (int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'big') >> 11) / 2**53
        eligible = attempt <= config.fail_first_attempts
        injected = eligible and draw < config.probability
        with self.tracer.span('fault_decision', SpanType.STATE_TRANSITION,
                              metadata={'engine_version': ENGINE_VERSION}) as event:
            event.output = {**config.model_dump(), 'target': target, 'attempt': attempt,
                            'draw': draw, 'eligible': eligible, 'injected': injected}
        return config.kind if injected else None
