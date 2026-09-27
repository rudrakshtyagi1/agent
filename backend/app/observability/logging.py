"""
Structured application logging for AgentGuard.

Design goals
------------
* JSON-structured log lines (when LOG_LEVEL != DEBUG) for easy ingestion into
  log aggregators (Loki, CloudWatch, etc.) in later phases.
* contextvars-based correlation so every log record emitted during a request
  lifecycle automatically carries run_id / trace_id / agent_id — without
  threading the IDs through every function call.
* Zero external dependencies in Phase 1.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Context variables for request-scoped correlation IDs
# ---------------------------------------------------------------------------

_run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "run_id", default=None
)
_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id", default=None
)
_agent_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "agent_id", default=None
)


def set_log_context(
    *,
    run_id: str | None = None,
    trace_id: str | None = None,
    agent_id: str | None = None,
) -> None:
    """Set correlation IDs in the current async context."""
    if run_id is not None:
        _run_id_var.set(run_id)
    if trace_id is not None:
        _trace_id_var.set(trace_id)
    if agent_id is not None:
        _agent_id_var.set(agent_id)


def clear_log_context() -> None:
    """Reset all correlation IDs in the current async context."""
    _run_id_var.set(None)
    _trace_id_var.set(None)
    _agent_id_var.set(None)


def get_log_context() -> dict[str, Any]:
    """Return the current correlation context as a dict."""
    ctx: dict[str, Any] = {}
    if (v := _run_id_var.get()) is not None:
        ctx["run_id"] = v
    if (v := _trace_id_var.get()) is not None:
        ctx["trace_id"] = v
    if (v := _agent_id_var.get()) is not None:
        ctx["agent_id"] = v
    return ctx


# ---------------------------------------------------------------------------
# Structured log formatter
# ---------------------------------------------------------------------------


class StructuredFormatter(logging.Formatter):
    """Emit JSON log lines enriched with correlation context."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Inject correlation context
        payload.update(get_log_context())
        # Attach exception info if present
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


# ---------------------------------------------------------------------------
# Public setup function
# ---------------------------------------------------------------------------


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure root logger with structured or human-readable formatting.

    Call this once during application startup (main.py lifespan).
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)

    # Use structured JSON in non-DEBUG environments; human-readable in DEBUG.
    if log_level.upper() == "DEBUG":
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    else:
        fmt = StructuredFormatter()

    handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(numeric_level)
    # Avoid duplicate handlers on repeated calls (e.g., during tests)
    if not root.handlers:
        root.addHandler(handler)
    else:
        root.handlers = [handler]
