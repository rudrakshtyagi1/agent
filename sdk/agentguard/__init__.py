"""Dependency-free completed-trace instrumentation for external Python agents."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import time
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from uuid import uuid4

__version__ = "0.1.0"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward tenant credentials to a redirect target.


class ExportError(RuntimeError):
    pass


class Trace:
    """Explicit export keeps network failures separate from agent execution.

    Use a separate Trace instance for each execution. Spans support nested async
    tasks via ContextVar; join child tasks before closing their parent span.
    Capture is opt-in. Never put secrets or personal information in span names.
    """

    def __init__(
        self,
        agent_name,
        agent_version,
        environment="development",
        capture_payloads=False,
    ):
        self.trace_id = str(uuid4())
        self.agent_name = agent_name
        self.agent_version = agent_version
        self.environment = environment
        self.capture_payloads = capture_payloads
        self.spans = []
        self._parent = ContextVar(f"agentguard-parent-{self.trace_id}", default=None)

    @contextmanager
    def span(self, name, span_type="tool_call", input=None):
        if len(self.spans) >= 200:
            raise ValueError("Trace span limit exceeded (200)")
        span = {
            "id": str(uuid4()),
            "parent_span_id": self._parent.get(),
            "name": name,
            "span_type": span_type,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "ended_at": None,
            "input": input if self.capture_payloads else None,
            "output": None,
            "metadata": {},
            "error": None,
            "input_tokens": None,
            "output_tokens": None,
        }
        self.spans.append(span)
        token = self._parent.set(span["id"])
        try:
            yield span
        except BaseException as error:
            span["error"] = (
                f"{type(error).__name__}: {error}"[:2000]
                if self.capture_payloads
                else type(error).__name__
            )
            raise
        finally:
            span["ended_at"] = datetime.now(timezone.utc).isoformat()
            self._parent.reset(token)

    def payload(self, status=None):
        roots = [s for s in self.spans if s["parent_span_id"] is None]
        if len(roots) != 1 or any(s["ended_at"] is None for s in self.spans):
            raise ValueError("Close all spans beneath a single root before exporting")
        spans = (
            self.spans
            if self.capture_payloads
            else [
                {**span, "input": None, "output": None, "metadata": {}}
                for span in self.spans
            ]
        )
        spans = json.loads(json.dumps(spans))
        return {
            "trace_id": self.trace_id,
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "environment": self.environment,
            "status": status or ("failed" if roots[0]["error"] else "completed"),
            "spans": spans,
        }

    def export(
        self, endpoint="http://127.0.0.1:8000", api_key=None, attempts=3, timeout=5
    ):
        if not 1 <= attempts <= 5 or not 0 < timeout <= 60:
            raise ValueError("Use 1–5 attempts and a timeout up to 60 seconds")
        data = json.dumps(self.payload()).encode()
        if len(data) > 524288:
            raise ExportError("Trace exceeds 512 KiB; reduce payload capture")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = "Bearer " + api_key
        request = Request(
            endpoint.rstrip("/") + "/api/v1/monitoring/traces",
            data=data,
            headers=headers,
            method="POST",
        )
        for attempt in range(attempts):
            try:
                with build_opener(NoRedirect).open(
                    request, timeout=timeout
                ) as response:
                    return json.load(response)
            except HTTPError as error:
                if error.code != 429 and error.code < 500:
                    raise ExportError(f"Trace rejected (HTTP {error.code})") from None
            except (URLError, TimeoutError):
                pass
            if attempt + 1 < attempts:
                time.sleep(min(0.2 * 2**attempt, 2))
        raise ExportError(
            "Trace export exhausted retry budget; retain Trace and retry with the same ID"
        )
