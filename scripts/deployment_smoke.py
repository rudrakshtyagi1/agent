"""Authenticated deployment acceptance check; no provider calls or secret output."""

import argparse
import json
import os
import sys
import time
from pathlib import Path
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk"))
from agentguard import Trace


def check(endpoint, key, previous=None):
    headers = {"Authorization": f"Bearer {key}"}
    with httpx.Client(base_url=endpoint, timeout=15, follow_redirects=False) as client:
        assert client.get("/ready").status_code == 200, "Readiness failed"
        page = client.get("/")
        assert page.status_code == 200 and "text/html" in page.headers.get(
            "content-type", ""
        ), "Dashboard missing"
        assert (
            client.get("/api/v1/monitoring/traces").status_code == 401
        ), "Anonymous access allowed"
        assert (
            client.get(
                "/api/v1/monitoring/traces", headers={"Authorization": "Bearer wrong"}
            ).status_code
            == 401
        ), "Invalid key accepted"
        assert (
            client.get("/api/v1/runs", headers=headers).status_code == 404
        ), "Local demo API exposed"
        if previous:
            assert (
                client.get(
                    f"/api/v1/monitoring/traces/{previous}", headers=headers
                ).status_code
                == 200
            ), "Persisted trace missing"
        trace = Trace("deployment-smoke", "1.0.0")
        with trace.span("synthetic-request", "planner"):
            with trace.span("synthetic-tool", "tool_call"):
                pass
        receipt = trace.export(endpoint, key, attempts=1)
        assert receipt["status"] == "queued", "Trace not queued"
        trace_id = receipt["id"]
        for _ in range(30):
            response = client.get(
                f"/api/v1/monitoring/traces/{trace_id}", headers=headers
            )
            response.raise_for_status()
            row = response.json()
            if row["status"] == "processed":
                break
            time.sleep(1)
        else:
            raise RuntimeError("Worker did not process trace")
        assert row["summary"]["span_count"] == 2
        return {
            "passed": True,
            "trace_id": trace_id,
            "previous_trace_verified": previous,
            "checks": [
                "readiness",
                "dashboard",
                "anonymous_denied",
                "wrong_key_denied",
                "demo_disabled",
                "ingestion",
                "processing",
            ],
            "endpoint": endpoint,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--previous-trace")
    parser.add_argument("--output", default="artifacts/deployment-smoke.json")
    args = parser.parse_args()
    key = os.environ.get("AGENTGUARD_API_KEY")
    if not key:
        parser.error(
            "Set AGENTGUARD_API_KEY in your shell; never pass it as a command argument"
        )
    try:
        result = check(args.endpoint, key, args.previous_trace)
    except Exception as error:
        print(
            f"Deployment check failed ({type(error).__name__}); response and credential suppressed.",
            file=sys.stderr,
        )
        sys.exit(1)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
