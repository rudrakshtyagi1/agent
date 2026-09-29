# Frozen holdout evaluation: runtime 1.2.0

Before the live run on 2026-09-29, Codex checked the four remaining labels against
`examples/support_data/policies.json` and `orders.json`. This is a policy consistency
review by the implementing assistant, not independent human validation. The dataset,
prompts, runtime and labels were left unchanged for this evaluation.

| Case | Order evidence | Policy rule | Expected decision |
| --- | --- | --- | --- |
| holdout-outside | Delivered 31 days ago; standard product | Refund window ends after day 30 | ineligible |
| holdout-exception | Delivered 4 days ago; final sale | Final sale is ineligible regardless of age | ineligible |
| holdout-undelivered | Not delivered; delivery age absent | Undelivered orders require human review | needs_review |
| holdout-unknown | DEMO-999 absent from order records | Unknown orders require human review | needs_review |

All cases require the refund-policy-v2 citation and a lookup of the requested order.
Evaluation checks decision labels, citation IDs and tool use, not every sentence's
faithfulness. These synthetic cases are too few for production reliability claims.
The previously exposed inclusive-boundary case stays in the regression split.

The live command uses the frozen grounded runtime only, without injected faults:

```bash
python scripts/run_groq_support.py --split holdout --limit 4 --max-requests 12 \
  --export --output artifacts/groq-holdout-v1.2.json
```

This is a single-pass evaluation, not a paired baseline comparison. Request-budget
exhaustion or provider errors must remain visible as incomplete/unmeasured results.
After this run these four cases are exposed evaluation cases; any tuning on their
outputs requires a fresh holdout for a new unbiased evaluation.

## Recorded outcome

All four cases passed the deterministic checks in one live run using 12 provider
requests. All four traces were confirmed processed by the local monitoring API.

| Case | Model decision | Checks | Requests | Reported tokens |
| --- | --- | --- | ---: | ---: |
| holdout-outside | ineligible | Pass | 3 | 1,973 |
| holdout-exception | ineligible | Pass | 3 | 1,956 |
| holdout-undelivered | needs_review | Pass | 3 | 1,943 |
| holdout-unknown | needs_review | Pass | 3 | 1,932 |

[Full measured report](groq-holdout-v1.2.json) includes answers, provenance, usage,
evaluations and persisted monitoring summaries. This is 4/4 on this synthetic
set, not evidence of 100% production accuracy. The summary’s paired-pass counts
are zero because no baseline was run; use `by_version.grounded` for this run.
