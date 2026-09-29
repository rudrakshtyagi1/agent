"""Small explicit Groq experiments; dry-run never loads a key or calls a provider."""

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "sdk")]
from dotenv import load_dotenv
from app.llm.groq import GroqClient, DEFAULT_MODEL, ProviderError
from app.target_agents.groq_support import run, DATA, PROMPT_VERSION
from app.evaluation.real_support import evaluate, summarize
from agentguard import ExportError


async def main(args):
    dataset = json.loads((ROOT / "evals/datasets/real_support/cases.json").read_text())
    selected = [c for c in dataset["cases"] if c["split"] == args.split][: args.limit]
    versions = ["baseline", "grounded"] if args.compare else ["grounded"]
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "mode": "dry_run" if args.dry_run else "live",
        "dataset_version": dataset["version"],
        "dataset_sha256": hashlib.sha256(
            json.dumps(dataset, sort_keys=True).encode()
        ).hexdigest(),
        "label_status": dataset["label_status"],
        "prompt_version": PROMPT_VERSION,
        "split": args.split,
        "case_ids": [c["id"] for c in selected],
        "versions": versions,
        "max_provider_requests": args.max_requests,
        "fault": args.fault,
        "cases": [],
        "limitations": [
            "Small synthetic suite; no production reliability estimate.",
            "Holdout cases are not used in prompts. Human label review is still required.",
            "No automatic paid-model fallback; account billing mode must be checked in Groq Console.",
        ],
    }
    if args.dry_run:
        print(json.dumps(manifest, indent=2))
        return 0
    load_dotenv(ROOT / ".env", override=False)
    key = os.getenv("GROQ_API_KEY")
    if not key:
        print(
            "Set a fresh GROQ_API_KEY in the local .env before running live tests.",
            file=sys.stderr,
        )
        return 2
    provider = GroqClient(key, model=args.model, max_requests=args.max_requests)
    exhausted = False
    for index, case in enumerate(selected):
        results = {}
        for version in (versions if index % 2 == 0 else list(reversed(versions))):
            if provider.requests >= args.max_requests:
                exhausted = True
                break
            trace, result = await run(
                provider, case["order_id"], case["question"], version, args.fault
            )
            result["evaluation"] = evaluate(result, case)
            if args.export:
                try:
                    result["telemetry"] = await asyncio.to_thread(
                        trace.export, args.monitor_url, os.getenv("AGENTGUARD_API_KEY")
                    )
                except ExportError as error:
                    result["telemetry"] = {
                        "status": "export_failed",
                        "error": str(error),
                    }
            else:
                result["telemetry"] = {"status": "not_requested"}
            results[version] = result
            # Stop on provider errors (including quota), not on decision failures.
            if result.get("failure_kind") == "provider":
                exhausted = True
                break
        manifest["cases"].append({"id": case["id"], "results": results})
        if exhausted:
            break
    manifest["provider_requests"] = provider.requests
    manifest["summary"] = summarize(manifest["cases"])
    manifest["complete"] = len(manifest["cases"]) == len(selected) and all(
        set(c["results"]) == set(versions) for c in manifest["cases"]
    )
    manifest["task_measurements_complete"] = all(
        r["evaluation"]["passed"] is not None
        for c in manifest["cases"]
        for r in c["results"].values()
    )
    manifest["passed"] = (
        manifest["complete"]
        and manifest["task_measurements_complete"]
        and all(
            r["evaluation"]["passed"]
            for c in manifest["cases"]
            for r in c["results"].values()
        )
    )
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    # The demo contains synthetic answers only. Never include a key or raw HTTP bodies.
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                "report": str(path),
                "complete": manifest["complete"],
                "passed": manifest["passed"],
                "task_measurements_complete": manifest["task_measurements_complete"],
                "provider_requests": provider.requests,
                "summary": manifest["summary"],
            },
            indent=2,
        )
    )
    return 0 if manifest["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--split", choices=["dev", "holdout"], default="dev")
    parser.add_argument("--limit", type=int, choices=range(1, 6), default=1)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--max-requests", type=int, choices=range(1, 13), default=4)
    parser.add_argument(
        "--fault",
        choices=["none", "missing_policy", "tool_timeout", "transient_tool_timeout"],
        default="none",
    )
    parser.add_argument(
        "--export", action="store_true", help="Export minimized telemetry to AgentGuard"
    )
    parser.add_argument("--monitor-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default="artifacts/groq-support-report.json")
    try:
        sys.exit(asyncio.run(main(parser.parse_args())))
    except (ValueError, ProviderError):
        print(
            "Invalid configuration. Check the selected model, budget, and local environment.",
            file=sys.stderr,
        )
        sys.exit(2)
