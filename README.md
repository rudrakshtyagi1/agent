# AgentGuard

AgentGuard is a testing and observability platform for multi-step AI agents.
Phase 5 includes an executable offline support agent, persisted nested traces,
a React trace explorer, a versioned evaluation engine, and paired chaos campaigns
with bounded retries, plus evidence-based failure diagnosis and symptom grouping.
Regression gates and live monitoring follow in later phases; see [ROADMAP.md](ROADMAP.md).

## Run locally

Python 3.11+ and Node.js 20.19+ are required. From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
make run
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173 and click **Run support agent** or **Simulate failure**.
Select a run, then a span to inspect timing, inputs, outputs, and errors.
The dashboard uses the real backend through Vite's `/api` development proxy.
API documentation is at http://127.0.0.1:8000/docs.

SQLite stores records in `agentguard_dev.db` in the server working directory.
Restart from the same directory to preserve the database location. Set
`DATABASE_URL` to use another database. The dashboard shows the latest 100 runs.

## Execution API

1. `POST /api/v1/agents` with `name`, `version: "1.0.0"`, and
   `endpoint: "builtin://support"`.
2. `POST /api/v1/test-cases` with a name and input, for example:
   `{"question":"Can I refund my order?","order_id":"ORD-1001","scenario":"success"}`.
3. `POST /api/v1/runs` with `agent_id`, `test_case_id`, and `agent_version`.
4. `POST /api/v1/runs/{id}/execute` to execute the queued run.
5. `GET /api/v1/runs/{id}/trace` or `GET /api/v1/traces/{trace_id}` to retrieve spans.

`ORD-1001` is within the refund window; `ORD-1002` is outside it. The
`tool_timeout` scenario deliberately fails the order lookup. Inputs are validated
and errors are retained in the trace. The answer generator is a deterministic
template, explicitly labeled as simulated; no API key or LLM is required.

Execution is bounded to 10 seconds and runs within the HTTP request. The final
status and trace commit together. Duplicate execution returns 409. A process
crash or request-task cancellation rolls back to queued; there is no background
job recovery or live streaming yet. Only the built-in adapter is executable;
registered HTTP URLs are not called. Create a new run to repeat a finished test.

This is a local development platform without authentication or automatic payload
redaction. Use fixture data. Production serving of the frontend needs an `/api`
reverse proxy; Vite's development proxy does not apply to static build output.

## Verify

```sh
make test
npm --prefix frontend run build
PYTHONPATH=backend python scripts/demo_trace.py
```

Tests cover nested tracing, concurrent ancestry, cancellation, API lifecycle,
failed runs, version/adapter checks, concurrent execution conflicts, and traces
surviving database engine/application recreation. The standalone script prints
an in-memory trace; dashboard runs persist to the database.

## Layout

- `backend/app/runtime/` — bounded adapter execution
- `backend/app/target_agents/` — built-in offline support agent
- `backend/app/tracing/` — instrumentation and trace persistence
- `backend/app/api/` — agent, test-case, run, and trace APIs
- `frontend/` — React/TypeScript trace explorer
- `evals/` — future evaluation datasets and suites

## Phase 3: evaluation engine

Open **Evaluation studio → Run evaluation suite** to execute the versioned
three-case support dataset. Saved reports can be reopened after restarting the
server. **Inspect run** opens the trace and its stored per-metric evaluations;
expand a metric and select an evidence link to inspect the supporting span.
Individual new runs can be scored with **Evaluate run** in the trace explorer.

The included dataset deliberately contains a timeout: the expected task success
is **2/3**, not 100%. It is a diagnostic fixture suite, not a held-out benchmark
or a claim about real-world agent reliability. Suite execution creates three
runs and an isolated registered demo agent. It is synchronous and transactional;
an infrastructure error rolls back the entire suite, while agent failures remain
valid case results.

### Metrics and interpretation

| Metric | Definition / limitation |
| --- | --- |
| Execution success | Whether the run completed; does not imply a correct answer. |
| Task success | Completed run with a final response matching every labeled top-level output field exactly (including nested values and JSON types). Missing labels give N/A. |
| Tool correctness | All required tools were called and no forbidden tool was called. Extra tools are allowed unless forbidden. Argument correctness and tool success are not scored here. |
| Retrieval recall | Unique relevant documents retrieved / unique relevant documents labeled. |
| Retrieval RR | Reciprocal of the first relevant rank; its suite mean is MRR. |
| Retrieval NDCG | Binary-relevance NDCG at the deduplicated retrieved depth. |
| Citation validity | Fraction of final-response citation IDs present in retrieved documents. Missing citations in an existing answer fail; missing answer gives N/A. |
| Groundedness | A **support-template-specific** verifier checks the complete refund answer, eligibility and citation against the recognized policy and recorded order age. It is not a general semantic/LLM judge; missing required evidence gives N/A. |
| Latency | Recorded execution duration in milliseconds; pass/fail only with a configured budget. |
| Token usage | Sum of real model spans' reported `usage.input_tokens` and `usage.output_tokens`. Partial, missing or simulated usage gives N/A, not zero. |

Retrieval metrics use a single deduplicated ranking across successful retrieval
spans in trace order. For multi-query agents, query-level evaluation will require
separate query labels. An empty ranking with known relevant documents scores
zero; missing relevance labels give N/A. A perfect retrieval score passes.

Each aggregate exposes its total, scored, unavailable, passed, and judged counts.
There is no combined score across unlike metrics. A mean of 100% groundedness
on two measured cases does not hide the third unavailable case. No token costs,
LLM-as-judge scores, or unmeasured metrics are fabricated.

### Label custom cases

When creating a test case, use the existing `expected_tools`, `forbidden_tools`,
and `expected_documents` fields, plus this validated metadata contract:

```json
{
  "metadata": {
    "evaluation": {
      "expected_output": {"eligible": true, "citations": ["refund-policy-v1"]},
      "max_latency_ms": 1000
    }
  }
}
```

Expectations are frozen in the root span when execution begins. Each evaluation
records the evaluator version, expectation SHA-256, trace ID, and evidence span
IDs. Natural-language `expected_behavior` is preserved but not automatically
judged. Phase 2 traces without snapshots cannot be retrospectively evaluated;
create a new run. Evaluation is independent of execution: evaluating a failed
run or encountering an evaluation error never rewrites the agent's outcome.

### Evaluation API and CLI

- `POST /api/v1/runs/{id}/evaluate`: compute and persist the current evaluator
  version once; repeated/concurrent requests return the same saved results.
- `GET /api/v1/runs/{id}/evaluations`: saved current-version results and summary.
- `GET /api/v1/evaluation-datasets`: bundled dataset information.
- `POST /api/v1/evaluation-suites/support-agent`: execute and save a suite report.
- `GET /api/v1/evaluation-suites`: recent report history.
- `GET /api/v1/evaluation-suites/{id}`: complete immutable suite report.

```sh
python scripts/run_evaluation_suite.py > /tmp/agentguard-evaluation.json
```

Dataset: `evals/datasets/golden/support_agent.json` (`support-refunds/1.0.0`).
Evaluator: `agentguard-rules/1.0.0`. Reports store both versions and the dataset
content hash. Keep the repository's `evals/` directory when running the backend;
the new `evaluation_suites` table is created additively at startup. Existing
runs and traces do not need to be deleted or migrated.

## Phase 4: chaos testing and recovery

Open **Chaos lab** and run a campaign. The default runs one clean baseline and
four pairs of faulted runs: one attempt without retries versus up to two attempts
with retries. Every pair uses the same agent, test case, expectations, seed,
and fault configuration. The original baseline and every run are inspectable.
Saved campaign reports survive server restart.

| Fault | Injection boundary | Agent behavior |
| --- | --- | --- |
| `tool_timeout` | Order lookup raises a synthetic timeout | Retry within budget; otherwise fail. |
| `malformed_tool` | Order age becomes an invalid string | Validate the response, retry; never use it to answer. |
| `missing_documents` | Retrieval returns an empty list | Require recognized policy evidence, retry or fail. |
| `irrelevant_retrieval` | Shipping policy replaces refund policy | Reject irrelevant evidence, retry or fail. |

Faults operate only on the built-in offline fixtures. They do not interrupt real
services, call external APIs, or exercise production infrastructure. These
failures are synthetic; they test agent handling and instrumentation.

### Reproducible decisions and bounded retries

- `seed` is an unsigned 32-bit integer. SHA-256 of the engine version, seed,
  fault kind, target, and attempt determines a probability draw. There is no
  shared RNG state; the same config produces the same decisions even across
  concurrent runs. Timings are not deterministic.
- `probability` ranges from 0 to 1. `fail_first_attempts` (1–3) controls the
  fault-eligible window; each eligible attempt gets its own deterministic draw.
  Later attempts are clean. A probability of 1 guarantees eligible injections;
  a probability of 0 injects nothing.
- `retry.max_attempts` (1–3) includes the first attempt, and applies per target.
  `retry.backoff_ms` (0–200) is multiplied by the failed attempt number. At most
  two backoff sleeps occur per step. Only timeouts and explicitly recoverable
  tool/retrieval validation errors are retried. Cancellation and unexpected
  programming errors propagate.
- The overall 10-second execution deadline includes retries and backoff. Traces
  retain attempted steps on deadline expiry. Campaigns are synchronous and
  transactional, with at most nine runs; no durable background worker is added.

The default four transient faults each fail without retries and recover with
two attempts. Set `fail_first_attempts: 3` and `max_attempts: 2` to demonstrate
exhaustion. Set `probability: 0` for a no-injection control: recovery becomes
**N/A**, not 100%.

Recovery means labeled task success after at least one fired fault in the retry
run. The denominator excludes runs where no fault fired. The report separately
counts tasks rescued by retries (failed without retries, passed with retries).
This small diagnostic sample is not a statistical production reliability claim.

Root span metadata stores the complete execution configuration, chaos engine
version, and support runtime version. Target spans record their attempt number;
`fault_decision` spans record the draw and whether a fault fired;
`retry_scheduled` spans record the reason and backoff. Malformed payloads and
retrieved documents remain visible on failed attempts. A retry schedule event
shows intent; target attempt spans confirm whether the retry actually began.

### Chaos API and CLI

- `GET /api/v1/chaos/faults`: available fault kinds and their targets.
- `POST /api/v1/chaos/campaigns`: run and persist a paired campaign.
- `GET /api/v1/chaos/campaigns`: saved campaign summaries.
- `GET /api/v1/chaos/campaigns/{id}`: complete report with run IDs and evidence.

Example campaign request:

```json
{
  "seed": 42,
  "probability": 1,
  "fail_first_attempts": 1,
  "faults": ["tool_timeout", "malformed_tool", "missing_documents", "irrelevant_retrieval"],
  "retry": {"max_attempts": 2, "backoff_ms": 20},
  "order_id": "ORD-1001"
}
```

For an existing queued run, pass execution options to
`POST /api/v1/runs/{id}/execute`:

```json
{
  "fault": {"kind": "tool_timeout", "seed": 42, "probability": 1, "fail_first_attempts": 1},
  "retry": {"max_attempts": 2, "backoff_ms": 20}
}
```

No body (or `{}`) preserves the original one-attempt, no-injection behavior.
The old test input `scenario: "tool_timeout"` remains an unconditional simulated
failure on every attempt, independent of the new fault injector. Campaigns use
`scenario: "success"` so all faults come from the recorded configuration.

```sh
python scripts/run_chaos_campaign.py > /tmp/agentguard-chaos.json
python scripts/run_chaos_campaign.py --fault-attempts 3 --max-attempts 2
python scripts/run_chaos_campaign.py --probability 0
```

`chaos_campaigns` is an additive table created at startup; existing data stays
intact. The adapter identifier remains `builtin://support` version `1.0.0` for
compatibility; traces additionally pin `support-runtime/2.0.0` to distinguish the
new retry and evidence-validation behavior from historical executions.

## Phase 5: failure intelligence

Open **Failure lab → Analyze recent runs** to diagnose the latest 20 finished
runs, including completed runs with failed checks and runs that recovered from
an intermediate failure. Select a symptom group and run to inspect the report;
**Failure evidence** and **Recovery evidence** open the exact trace span.
Individual traces also have a **Diagnose run** action.

The rule engine identifies tool timeouts, invalid order-tool payloads, missing
retrieval documents, irrelevant document IDs, input validation errors, and
execution deadlines. It also incorporates failed reference-answer, citation,
groundedness, tool-selection, retrieval-recall, and latency checks. It does not
call an LLM or claim access to external service internals.

### Evidence and causal limits

- Repeated copies of the same exception in ancestor spans are treated as
  propagation, not independent causes. Error timing uses span completion time.
- The primary finding favors unresolved observed failures over downstream checks
  and recovered incidents. This is an evidence ordering, not proof of causality
  among concurrent branches.
- Recovery requires a later successful attempt with the same step name, parent,
  and input. A recovered step does not imply that the entire task succeeded;
  report outcome and task verdict are separate.
- A reference mismatch means the output differs from the frozen reference. It
  does not prove the reference is correct. Groundedness inherits Phase 3's narrow
  support-template scope.
- Failure without a localized span produces **unknown**. A clean trace produces
  **no failure observed**, not a guarantee of correctness. Legacy traces can be
  diagnosed even when their evaluation snapshot is unavailable.
- A recorded injected fault is associated only with its failed parent step.
  Injection provenance is separate from classification. The classifier never
  uses a configured fault kind to guess what failed.
- Explanations separate observed conditions from possible causes and provide
  concrete next checks. No invented confidence probabilities are displayed.

Findings retain observed errors/payloads, span IDs, evaluation IDs, recovery
spans, and the diagnosis version (`agentguard-diagnosis/1.0.0`). Diagnoses are
saved once per run and version, including clean results, and repeated/concurrent
requests return the same report. A diagnosis error does not rewrite execution
status. Changed diagnosis rules require a version bump; reports are immutable.

### Similar failures

Failure Lab groups the **most recent 500 failure records** by category, subtype,
and component, reporting the window explicitly. These are exact symptom
signatures, not embedding clusters and not evidence that all grouped runs have
the same root cause. Group occurrences count findings, which may include multiple
independent scopes in one run. Recovered and unresolved findings remain visible.

### Blinded fixture audit

Click **Run diagnosis audit** to create a nine-run chaos campaign (four failed
runs, four recoveries, and a clean baseline), classify it, and save the audit.
Before each audit prediction, injector-decision spans and root execution/fault
configuration are removed. Expected labels are compared only after diagnosis.
The full diagnoses retain injection provenance for developer inspection.

The audit checks both symptom subtype and run outcome. **9/9** on these fixtures
is a regression check, not held-out accuracy or a production reliability claim.
Tests additionally cover unknown evidence, incorrect references, propagated
errors, deadlines, wrong configured fault labels, and an error recurring after
an earlier recovery.

```sh
python scripts/run_diagnosis_audit.py > /tmp/agentguard-diagnosis-audit.json
```

The script exits nonzero if any fixture prediction differs from its label.

### Diagnosis API

- `POST /api/v1/runs/{id}/diagnose`: evaluate when possible, then diagnose and save.
- `GET /api/v1/runs/{id}/diagnosis`: saved current-version report, or `null` if not analyzed.
- `POST /api/v1/failures/analyze-recent?limit=20`: analyze 1–50 most recent finished runs.
- `GET /api/v1/failures/groups`: bounded symptom groups and related run IDs.
- `POST /api/v1/failures/benchmark`: create and save the blinded fixture audit.
- `GET /api/v1/failures/benchmarks/latest`: last saved audit, or `null`.

`run_diagnoses` and `diagnosis_benchmarks` are additive tables created at startup;
findings use the existing `failures` table. No existing records need deletion.
The local service remains unauthenticated and the entire analysis request uses
a database transaction. Durable workers, production monitoring, and general
LLM-based investigation are outside this phase.
