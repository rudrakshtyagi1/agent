"""Explicit synthetic decision checks, not semantic quality or LLM-as-judge."""

import hashlib
import json

VERSION = "support-decision-checks/1.0.0"


def evaluate(result, case):
    answer = result.get("answer") or {}
    checks = {
        "execution_completed": result["status"] == "completed",
        "decision_matches": answer.get("decision") == case["expected_decision"],
        "required_citations": set(case["expected_citations"])
        <= set(answer.get("citations", [])),
        "citations_retrieved": bool(answer.get("citations"))
        and set(answer["citations"]) <= set(result["retrieved_ids"]),
        "requested_order_read": any(
            c["name"] == "lookup_order"
            and c["arguments"].get("order_id") == case["order_id"]
            for c in result["tool_calls"]
        ),
    }
    return {
        "evaluator_version": VERSION,
        "case_sha256": hashlib.sha256(
            json.dumps(case, sort_keys=True).encode()
        ).hexdigest(),
        "passed": (
            None if result.get("failure_kind") == "provider" else all(checks.values())
        ),
        "measurement_status": (
            "provider_unavailable"
            if result.get("failure_kind") == "provider"
            else "measured"
        ),
        "checks": checks,
        "limitation": "Checks decision labels, citation IDs, and tool use; does not grade prose faithfulness or semantic correctness.",
    }


def summarize(cases):
    paired = [
        c
        for c in cases
        if set(c["results"]) == {"baseline", "grounded"}
        and all(r["evaluation"]["passed"] is not None for r in c["results"].values())
    ]
    by_version = {}
    for version in ("baseline", "grounded"):
        values = [
            c["results"][version]["evaluation"]["passed"]
            for c in cases
            if version in c["results"]
        ]
        by_version[version] = {
            "attempted": len(values),
            "measured": sum(v is not None for v in values),
            "passes": sum(v is True for v in values),
            "unavailable": sum(v is None for v in values),
        }
    return {
        "by_version": by_version,
        "cases_run": len(cases),
        "paired_cases": len(paired),
        "unmeasured_or_unpaired_cases": len(cases) - len(paired),
        "baseline_passes": sum(
            c["results"]["baseline"]["evaluation"]["passed"] for c in paired
        ),
        "grounded_passes": sum(
            c["results"]["grounded"]["evaluation"]["passed"] for c in paired
        ),
        "regressions": [
            c["id"]
            for c in paired
            if c["results"]["baseline"]["evaluation"]["passed"]
            and not c["results"]["grounded"]["evaluation"]["passed"]
        ],
        "improvements": [
            c["id"]
            for c in paired
            if not c["results"]["baseline"]["evaluation"]["passed"]
            and c["results"]["grounded"]["evaluation"]["passed"]
        ],
    }
