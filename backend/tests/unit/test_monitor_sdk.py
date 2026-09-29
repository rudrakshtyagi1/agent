import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sdk"))
from agentguard import Trace, ExportError
from app.monitoring.schemas import IncomingTrace


def test_sdk_exception_ancestry_and_capture_defaults():
    trace = Trace("real-agent", "1")
    with pytest.raises(ValueError):
        with trace.span("root", "planner"):
            with trace.span("tool", input={"password": "private"}) as span:
                span["output"] = {"sensitive": "value"}
                raise ValueError("secret message")
    payload = trace.payload()
    assert payload["status"] == "failed"
    assert payload["spans"][1]["parent_span_id"] == payload["spans"][0]["id"]
    assert "private" not in str(payload) and "secret message" not in str(payload)
    assert payload["spans"][1]["output"] is None
    IncomingTrace.model_validate(payload)


def test_sdk_requires_closed_single_root_and_bounded_export():
    trace = Trace("a", "1")
    with trace.span("root", "planner"):
        with pytest.raises(ValueError):
            trace.payload()
    with pytest.raises(ValueError):
        trace.export(attempts=100)
    with trace.span("another-root", "planner"):
        pass
    with pytest.raises(ValueError):
        trace.payload()


def test_default_capture_discards_non_serializable_results():
    trace = Trace("a", "1")
    with trace.span("root", "planner") as span:
        span["output"] = object()
    assert trace.payload()["spans"][0]["output"] is None


def test_export_retries_same_payload_and_rejects_redirects(monkeypatch):
    import agentguard
    from urllib.error import HTTPError
    import io

    trace = Trace("a", "1")
    with trace.span("root", "planner"):
        pass
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request.data)
            if len(requests) == 1:
                raise HTTPError(request.full_url, 429, "busy", {}, None)
            return io.BytesIO(b'{"status":"queued"}')

    monkeypatch.setattr(agentguard, "build_opener", lambda *args: Opener())
    monkeypatch.setattr(agentguard.time, "sleep", lambda _: None)
    assert trace.export()["status"] == "queued"
    assert len(requests) == 2 and requests[0] == requests[1]

    class Redirect:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, 302, "redirect", {}, None)

    monkeypatch.setattr(agentguard, "build_opener", lambda *args: Redirect())
    with pytest.raises(ExportError, match="302"):
        trace.export()
    assert (
        agentguard.NoRedirect().redirect_request(
            None, None, 302, "", {}, "https://other"
        )
        is None
    )
