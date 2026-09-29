"""Contract tests use scripted HTTP responses, never real provider credentials."""

import json
from pathlib import Path
import httpx
import pytest
from agentguard import Trace
from app.llm.groq import GroqClient, ProviderError, BudgetExceeded
from app.target_agents.groq_support import run, DATA
from app.rag.bm25 import search
from app.evaluation.real_support import evaluate, summarize


def tc(name, args, id="call-1"):
    return {
        "id": id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def reply(tools=None, answer=None, usage=True):
    return {
        "choices": [
            {
                "finish_reason": "tool_calls" if tools else "stop",
                "message": {
                    "role": "assistant",
                    "tool_calls": tools,
                    "content": (
                        None
                        if tools
                        else json.dumps(
                            answer
                            or {
                                "decision": "eligible",
                                "answer": "Eligible under the refund policy.",
                                "citations": ["refund-policy-v2"],
                            }
                        )
                    ),
                    "reasoning": "never store this",
                },
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5} if usage else None,
    }


def sequence():
    return [
        reply([tc("search_policy", {"query": "refund eligibility"})]),
        reply([tc("lookup_order", {"order_id": "DEMO-001"}, "call-2")]),
        reply(),
    ]


async def execute(responses, **kwargs):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        assert request.url.host == "api.groq.com"
        return httpx.Response(200, json=responses.pop(0))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        provider = GroqClient("test-only-key", client=http, interval_seconds=0)
        trace, result = await run(provider, **kwargs)
    return trace, result, requests


@pytest.mark.asyncio
async def test_real_tool_loop_usage_and_no_reasoning_or_credentials_in_trace():
    trace, result, requests = await execute(sequence())
    assert result["status"] == "completed", result
    assert result["answer"]["decision"] == "eligible"
    assert result["reported_tokens"] == 45
    assert [c["name"] for c in result["tool_calls"]] == [
        "search_policy",
        "lookup_order",
    ]
    assert requests[-1]["messages"][-1]["role"] == "user"
    final_evidence = json.loads(requests[-1]["messages"][-1]["content"])
    assert final_evidence["order"]["order_id"] == "DEMO-001"
    assert "expected_decision" not in final_evidence
    assert all(m["role"] != "tool" for m in requests[-1]["messages"])
    assert requests[0]["tool_choice"] == "auto"
    assert requests[-1]["tool_choice"] == "none"
    assert requests[-1]["response_format"] == {"type": "json_object"}
    assert "tools" not in requests[-1]
    assert "parallel_tool_calls" not in requests[-1]
    assert result["provenance"]["runtime_version"] == "groq-support-runtime/1.2.0"
    assert "refund-policy-v2" in requests[1]["messages"][-1]["content"]
    serialized = json.dumps(trace.payload())
    assert "never store this" not in serialized and "test-only-key" not in serialized
    assert all(
        s["input"] is None and s["output"] is None for s in trace.payload()["spans"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "call,error",
    [
        (tc("shell", {"command": "anything"}), "allowlist"),
        (tc("lookup_order", {"order_id": "DEMO-002"}), "unrelated"),
        (
            tc("lookup_order", {"order_id": "DEMO-001", "extra": "value"}),
            "invalid tool",
        ),
    ],
)
async def test_untrusted_model_tools_rejected(call, error):
    trace, result, _ = await execute([reply([call])])
    assert result["status"] == "failed" and error in result["error"]
    assert all(s["ended_at"] for s in trace.spans)


@pytest.mark.asyncio
async def test_transient_timeout_fix_is_visible_and_persistent_timeout_fails():
    trace, baseline, _ = await execute(
        sequence(), version="baseline", fault="transient_tool_timeout"
    )
    assert baseline["status"] == "failed"
    trace, grounded, _ = await execute(sequence(), fault="transient_tool_timeout")
    assert grounded["status"] == "completed"
    attempts = [s for s in trace.spans if s["name"] == "lookup_order_attempt"]
    assert len(attempts) == 2 and attempts[0]["error"] and not attempts[1]["error"]
    _, persistent, _ = await execute(sequence(), fault="tool_timeout")
    assert persistent["status"] == "failed"


@pytest.mark.asyncio
async def test_missing_evidence_and_answer_schema_fail_closed():
    _, result, _ = await execute(sequence(), fault="missing_policy")
    assert result["status"] == "failed" and "evidence" in result["error"]
    _, result, _ = await execute([reply(answer={"decision": "eligible"})])
    assert result["status"] == "failed" and "JSON contract" in result["error"]
    _, result, _ = await execute([reply()])
    assert result["status"] == "failed" and "before looking up" in result["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 429, 500, 302])
async def test_provider_errors_are_sanitized_and_not_retried(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, json={"error": "private provider body test-only-key"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        provider = GroqClient("test-only-key", client=http, interval_seconds=0)
        trace, result = await run(provider)
    assert (
        len(calls) == 1
        and result["status"] == "failed"
        and result["failure_kind"] == "provider"
    )
    assert "private provider body" not in json.dumps(result)
    case = {
        "expected_decision": "eligible",
        "expected_citations": ["refund-policy-v2"],
        "order_id": "DEMO-001",
    }
    assert evaluate(result, case)["passed"] is None


@pytest.mark.asyncio
async def test_provider_budget_and_response_limits():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=reply()))
    ) as http:
        provider = GroqClient("test", max_requests=1, interval_seconds=0, client=http)
        trace = Trace("test", "v1")
        with trace.span("root", "planner"):
            await provider.complete([], [], trace)
            with pytest.raises(BudgetExceeded):
                await provider.complete([], [], trace)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=b"x" * 65537)
        )
    ) as http:
        trace, result = await run(GroqClient("test", interval_seconds=0, client=http))
        assert "64 KiB" in result["error"]


def test_retrieval_is_ranked_and_zero_overlap_stays_empty():
    documents = json.loads((DATA / "policies.json").read_text())["documents"]
    assert search(documents, "refund eligibility")[0]["id"] == "refund-policy-v2"
    assert search(documents, "zzzznothing") == []
    assert search(documents, "refund eligibility") == search(
        documents, "refund eligibility"
    )


def test_holdout_split_disjoint_and_comparison_excludes_missing_measurements():
    dataset = json.loads(
        (DATA.parent.parent / "evals/datasets/real_support/cases.json").read_text()
    )
    dev = {c["id"] for c in dataset["cases"] if c["split"] == "dev"}
    holdout = {c["id"] for c in dataset["cases"] if c["split"] == "holdout"}
    assert not dev & holdout and len(dev) == 2 and len(holdout) == 4
    assert {c["id"] for c in dataset["cases"] if c["split"] == "regression"} == {
        "holdout-inclusive"
    }
    report = summarize(
        [
            {
                "id": "a",
                "results": {
                    "baseline": {"evaluation": {"passed": True}},
                    "grounded": {"evaluation": {"passed": None}},
                },
            }
        ]
    )
    assert report["paired_cases"] == 0 and report["unmeasured_or_unpaired_cases"] == 1


@pytest.mark.asyncio
async def test_cli_dry_run_never_loads_credentials_and_live_report_is_explicit(
    tmp_path, monkeypatch, capsys
):
    import importlib.util
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location(
        "groq_command", DATA.parent.parent / "scripts/run_groq_support.py"
    )
    command = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(command)

    def forbidden(*args, **kwargs):
        raise AssertionError("dry-run must not load .env")

    monkeypatch.setattr(command, "load_dotenv", forbidden)
    args = SimpleNamespace(
        split="dev",
        limit=1,
        compare=False,
        dry_run=True,
        model="test-model",
        max_requests=4,
        fault="none",
        export=False,
        output=str(tmp_path / "report.json"),
    )
    assert await command.main(args) == 0
    manifest = json.loads(capsys.readouterr().out)
    assert (
        manifest["mode"] == "dry_run"
        and manifest["cases"] == []
        and not Path(args.output).exists()
    )
    monkeypatch.setattr(command, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("GROQ_API_KEY", "test-only-key")
    responses = sequence()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=responses.pop(0))
        )
    ) as http:
        monkeypatch.setattr(
            command,
            "GroqClient",
            lambda key, **kw: GroqClient(key, client=http, interval_seconds=0, **kw),
        )
        args.dry_run = False
        assert await command.main(args) == 0
    report = json.loads(Path(args.output).read_text())
    assert report["mode"] == "live" and report["passed"] and report["complete"]
    assert report["summary"]["by_version"]["grounded"] == {
        "attempted": 1,
        "measured": 1,
        "passes": 1,
        "unavailable": 0,
    }
    assert "test-only-key" not in Path(args.output).read_text()
    # 'live' identifies the command path; this test still uses mocked HTTP.


@pytest.mark.asyncio
async def test_final_generation_rejects_unexpected_tool_calls():
    replies = sequence()
    replies[-1] = reply([tc("search_policy", {"query": "refund"}, "call-3")])
    _, result, requests = await execute(replies)
    assert requests[-1]["tool_choice"] == "none"
    assert result["status"] == "failed" and result["failure_kind"] == "provider"
    assert (
        len(result["tool_calls"]) == 2
    )  # The unexpected third call is never executed.
