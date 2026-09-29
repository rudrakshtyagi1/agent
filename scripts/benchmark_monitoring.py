"""Measure local SDK instrumentation and HTTP admission, not production throughput."""

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk"))
from agentguard import Trace, ExportError


def percentile(values, p):
    return sorted(values)[math.ceil(len(values) * p) - 1]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--output", default="/tmp/agentguard-monitor-benchmark.json")
    args = parser.parse_args()
    if not 1 <= args.count <= 1000:
        parser.error("count must be 1–1000")
    instrumentation = []
    bare = []
    admission = []
    outcomes = {}
    failed = 0
    for i in range(args.count):
        start = time.perf_counter()
        hashlib.sha256(b"agentguard" * 100).hexdigest()
        bare.append((time.perf_counter() - start) * 1000)
        start = time.perf_counter()
        trace = Trace("instrumentation-benchmark", "1.0.0")
        with trace.span("hash-document", "planner"):
            with trace.span("sha256", "tool_call"):
                hashlib.sha256(b"agentguard" * 100).hexdigest()
        instrumentation.append((time.perf_counter() - start) * 1000)
        start = time.perf_counter()
        try:
            result = trace.export(
                args.endpoint, os.getenv("AGENTGUARD_API_KEY"), attempts=1
            )
            outcomes[result["status"]] = outcomes.get(result["status"], 0) + 1
        except ExportError:
            failed += 1
        admission.append((time.perf_counter() - start) * 1000)
    result = {
        "platform": platform.system() + " " + platform.machine(),
        "python": platform.python_version(),
        "samples": args.count,
        "span_count_per_trace": 2,
        "bare_median_ms": statistics.median(bare),
        "instrumented_median_ms": statistics.median(instrumentation),
        "instrumented_p95_ms": percentile(instrumentation, 0.95),
        "median_overhead_ms": statistics.median(instrumentation)
        - statistics.median(bare),
        "http_admission_median_ms": statistics.median(admission),
        "http_admission_p95_ms": percentile(admission, 0.95),
        "responses": outcomes,
        "failed_submissions": failed,
        "unaccepted_spans": 2 * (failed + outcomes.get("sampled_out", 0)),
        "limitations": [
            "Sequential local HTTP requests; no concurrency/load capacity claim.",
            "Admission latency ends at durable enqueue, not worker completion.",
            "Instrumentation sample includes UUIDs/context setup; no LLM calls.",
        ],
    }
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
