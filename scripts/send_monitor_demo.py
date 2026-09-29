"""Send actual local retrieval/tool timings through the external SDK."""

import argparse
import hashlib
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk"))
from agentguard import Trace


def run(fail=False):
    trace = Trace("document-checker", "1.0.0")
    try:
        with trace.span("check-document", "planner"):
            with trace.span("read-project-description", "retrieval") as span:
                document = (
                    Path(__file__).resolve().parents[1] / "README.md"
                ).read_text()
                span["output"] = {"characters": len(document)}
            with trace.span("checksum", "tool_call") as span:
                if fail:
                    raise ValueError("Demonstration tool failure")
                span["output"] = {
                    "sha256": hashlib.sha256(document.encode()).hexdigest()
                }
    except ValueError:
        pass
    return trace


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000")
    parser.add_argument("--count", type=int, default=6)
    parser.add_argument("--fail-every", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.count <= 1000 or args.fail_every < 0:
        parser.error("count must be 1–1000; fail-every must be nonnegative")
    for i in range(args.count):
        trace = run(bool(args.fail_every and (i + 1) % args.fail_every == 0))
        print(trace.export(args.endpoint, os.getenv("AGENTGUARD_API_KEY")))
