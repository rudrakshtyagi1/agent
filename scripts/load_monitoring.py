"""Bounded synthetic HTTP ingestion check, not a production capacity benchmark."""

import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk"))
from agentguard import Trace


async def run(args):
    semaphore = asyncio.Semaphore(args.concurrency)
    durations, receipts = [], []
    failures = 0
    key = os.environ["AGENTGUARD_API_KEY"]
    started = time.perf_counter()

    async def submit():
        nonlocal failures
        async with semaphore:
            trace = Trace("bounded-load-check", "1.0.0")
            with trace.span("synthetic-operation", "planner"):
                pass
            start = time.perf_counter()
            try:
                receipt = await asyncio.to_thread(
                    trace.export, args.endpoint, key, attempts=1
                )
                if receipt["status"] == "queued":
                    receipts.append(receipt["id"])
                else:
                    failures += 1
            except Exception:
                failures += 1
            durations.append((time.perf_counter() - start) * 1000)

    await asyncio.gather(*(submit() for _ in range(args.count)))
    admission_seconds = time.perf_counter() - started
    pending = set(receipts)
    dead = 0
    deadline = time.monotonic() + 60
    async with httpx.AsyncClient(
        base_url=args.endpoint, headers={"Authorization": f"Bearer {key}"}, timeout=10
    ) as client:
        while pending and time.monotonic() < deadline:
            for tid in list(pending):
                response = await client.get(f"/api/v1/monitoring/traces/{tid}")
                response.raise_for_status()
                status = response.json()["status"]
                if status in ("processed", "dead_letter"):
                    pending.remove(tid)
                    dead += status == "dead_letter"
            if pending:
                await asyncio.sleep(1)
    return {
        "count": args.count,
        "concurrency": args.concurrency,
        "accepted": len(receipts),
        "failed_or_sampled": failures,
        "processed": len(receipts) - len(pending) - dead,
        "dead_letter": dead,
        "pending_after_60s": len(pending),
        "admission_seconds": admission_seconds,
        "admission_median_ms": statistics.median(durations),
        "admission_p95_ms": sorted(durations)[math.ceil(0.95 * len(durations)) - 1],
        "passed": not failures and not pending and not dead,
        "limitations": [
            "Synthetic local Docker/PostgreSQL workload; no AWS capacity claim.",
            "Admission latency includes SDK HTTP overhead; completion checked separately.",
            "No provider calls; no LLM quality or sustained-load claim.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--count", type=int, choices=range(1, 201), default=50)
    parser.add_argument("--concurrency", type=int, choices=range(1, 11), default=5)
    parser.add_argument("--output", default="artifacts/load-check.json")
    args = parser.parse_args()
    if not os.environ.get("AGENTGUARD_API_KEY"):
        parser.error("Set AGENTGUARD_API_KEY in the environment")
    try:
        result = asyncio.run(run(args))
    except Exception as error:
        print(
            f"Load check failed ({type(error).__name__}); details suppressed",
            file=sys.stderr,
        )
        sys.exit(1)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)
