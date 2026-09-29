# AgentGuard

AgentGuard is a testing and observability platform for multi-step AI agents.
Phase 7 includes an executable offline support agent, persisted nested traces,
a React trace explorer, a versioned evaluation engine, and paired chaos campaigns
with bounded retries, plus evidence-based failure diagnosis and symptom grouping.
Paired regression gates and strict recorded-response replay are available. External telemetry and live monitoring are available; see [ROADMAP.md](ROADMAP.md).

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

## Phase 6: regression gates and recorded playback

Regression Lab executes baseline and candidate versions against the same five
frozen support cases: ordinary eligibility, expiry, both sides of the 30-day
boundary, and a transient timeout. Versions are executable configurations:
`1.0.0` uses one attempt; `1.1.0` uses two; `1.1.0-regression` deliberately uses
an incorrect 7-day window. With default gates, the improved candidate passes
5/5 versus baseline 4/5. The faulty candidate passes 2/5 and introduces two
regressions. These are diagnostic fixtures, not a held-out production benchmark.

Reports persist in the additive `regression_reports` table. They include paired
run IDs, per-case changes, overlapping slices, evaluation/expectation compatibility,
dataset SHA-256, runtime/model/prompt/tool versions, execution options and gate
checks. Missing or incompatible task measurements block a release. Defaults
require five measured pairs, no regressions and 100% candidate task success.
Optional mean latency increase checks require complete latency measurements;
single-run fixture timings are noisy. The illustrative 95% Hoeffding interval
assumes independent representative cases; this fixed suite does not establish
population reliability. It is shown as context and is not a gate criterion.

```bash
# No running server required; creates an isolated temporary SQLite database.
python scripts/check_release.py --output release-report.json
# Expected rejection (exit 1):
python scripts/check_release.py --candidate-version 1.1.0-regression --output rejected-report.json
```

CLI exit codes: **0** accepted, **1** failed/blocked, **2** execution/configuration
error. `--max-regressions` and `--min-success-rate` configure the CLI gate.
GitHub Actions runs the default gate and uploads its JSON report. CLI run IDs
refer to the temporary database, which is removed afterward; use API/dashboard
comparisons for retained traces. The JSON embeds evaluation and fault evidence.

API endpoints:

- `GET /api/v1/regressions/versions`: executable version registry and provenance.
- `POST /api/v1/regressions/compare`: `baseline_version`, `candidate_version`,
  and `gate` (`max_regressions`, `min_task_success_rate`, `min_measured_cases`,
  optional `max_mean_latency_increase_ms`). Returns a saved report.
- `GET /api/v1/regressions/reports` and `/reports/{id}`: history and full report.
- `POST /api/v1/runs/{id}/replay`: `{"candidate_version":"1.1.0"}` creates a new
  execution using the source trace's frozen input and recorded retrieval/tool
  outputs and supported errors. It matches ordered call names and inputs exactly.
  Missing, mismatched or unconsumed responses fail explicitly; there is no fallback
  to fixture or external calls. Candidate answer generation executes again;
  model randomness and original timings are not reproduced. Each replay boundary
  links its original span, and root metadata saves source IDs and snapshot hash.

A source that failed after one timeout cannot supply an improved candidate's
additional retry: strict playback fails in that case. Run a paired comparison
to measure recovery with fresh fixture responses. Playback supports only the
built-in support agent's complete, recognized boundary records. Existing legacy
traces without frozen inputs are rejected. Ordinary execution with no options
body uses the selected version's retry profile; explicit options (including `{}`)
use the supplied policy/defaults, which can override that profile.

## Phase 7: external telemetry and live monitoring

Live Monitoring receives completed traces from external Python agents, processes
an authenticated durable inbox, and displays execution health and alert history.
The Python SDK wraps **your existing calls**; it does not replace your agent or
require an LLM provider. The demonstration records actual file retrieval and
hashing, with a deliberately raised tool exception every third run:

```bash
pip install -e ./sdk
python scripts/send_monitor_demo.py --count 6
# For authenticated servers, set AGENTGUARD_API_KEY in your shell first.
```

Open **Live monitoring** in the dashboard. Six demo submissions generate an
execution failure-rate alert (2/6) after the worker processes them. Alert evidence
opens the external trace and its nested spans. The page refreshes every three
seconds and supports pause/resume. API keys remain in component memory, never
localStorage. For an existing agent, use `Trace` and `trace.span()` around its
planner/retrieval/model/tool steps, then explicitly call `trace.export()` after
all spans close. See [sdk/agentguard](sdk/agentguard/__init__.py). Async callers
should move the blocking exporter to a thread. Capture token counts by assigning
`input_tokens` and `output_tokens` on each model span; incomplete coverage stays
unavailable. Execution status is producer-reported; it is **not task success**.

### Ingestion and worker contract

- `POST /api/v1/monitoring/traces` accepts one completed, single-root tree (up to
  200 spans and 512 KiB). UUIDs, timezone-aware timestamps, parent references,
  cycles and child timing are validated. No arbitrary endpoint is executed.
- A 202 response with `queued` means the minimized trace has committed to the
  database inbox. `sampled_out` means the configured deterministic head sampler
  intentionally omitted it. This is not a worker-completion response.
- Retries with the same tenant/trace ID and identical **retained** content return
  the existing record; changed retained content returns 409. Idempotency lasts
  until retention deletion. Capacity exhaustion returns 429; the sender should
  retry with the same ID. The SDK retries network errors, 429 and 5xx at most
  three times by default, never follows redirects, and raises `ExportError` on
  exhaustion. The caller owns durable sender-side buffering; it must retain a
  failed Trace if it wants to retry later.
- One lifespan worker processes at most 25 rows per transaction. Queue rows
  survive restarts; summary/alert updates commit atomically. Unexpected processing
  failures leave the queue for retry and appear in worker health. Invalid stored
  rows become visible dead letters. A single process lock serializes admission
  and worker transactions. **Run exactly one API worker/process.** Multi-process
  claiming, distributed queues and horizontal scaling are not implemented.
- Pending capacity is global, while all reads/writes and alerts are tenant-scoped.
  Counters show accepted traces, sampled-out/rejected *submissions*, and their
  omitted spans; retrying a rejected submission can increment these counters
  again. They do not claim unique permanently lost traces. HTTP/auth/validation
  rejections and sender-side failures are not included in those counters.
- Retention deletes old inbox/processed/dead-letter rows and old alert records
  using server ingestion time. Default: seven days. Pending rows can also expire.
  Aggregate admission counters remain. Backup deletion is an operator concern.

`GET /api/v1/monitoring/overview`, `/traces`, `/traces/{id}` and `/alerts` expose
only the authenticated tenant. Detail IDs are server-generated IDs returned on
admission. External telemetry lives in separate additive tables; it never enters
the development-only unscoped run/evaluation APIs.

### Authentication, privacy, and deployment

Set `APP_ENV=staging` or `production` and `MONITOR_KEYS` to a JSON mapping of tenant
names to unique random bearer keys (at least 32 characters each). Generate each
key with `python -c 'import secrets; print(secrets.token_urlsafe(32))'` and store
it in your deployment secret manager. Send `Authorization: Bearer <key>`.
The server derives tenant scope from the key; clients cannot choose a tenant in
trace JSON. Invalid/missing keys get 401, cross-tenant detail IDs get 404. Keys
permit both ingestion and reading within one tenant; fine-grained RBAC and a key
management UI are not implemented. Rotate/revoke by changing the mapping and
restarting. In development only, an empty mapping enables the `local-demo` tenant.

Outside development, all legacy demo endpoints and API docs are disabled.
Health and authenticated monitoring remain available. Build the dashboard with
`VITE_MONITOR_ONLY=true npm --prefix frontend run build` to hide demo navigation
and open monitoring directly. Serve this static build and proxy `/api/v1/monitoring`
to the backend under the same HTTPS origin. Use one uvicorn worker, a persistent
database volume, TLS at the reverse proxy, request timeouts and per-key/IP rate
limits at the ingress. These deployment components are not provisioned here.
SQLite is tested; PostgreSQL configuration exists but this monitoring milestone
has not been load-tested or validated against PostgreSQL.

Payload capture defaults **off on both SDK and server**. Inputs, outputs and
metadata are discarded before storage; error text is replaced with a generic
marker. When explicitly enabled on both, recursive filtering removes known
sensitive keys, email addresses, common phone patterns and token strings before
persistence. This is best-effort pattern filtering, not a PII guarantee. Never
put secrets in agent/span names or identifiers. Validation responses do not echo
submitted values; monitoring errors suppress exception payloads in application
logs. Do not enable raw request logging at your proxy.

### Alerts and measurements

Each agent/version/environment has a trailing window of up to 50 retained
executions, ordered by server ingestion time. With at least five observations,
failure rate ≥20% or nearest-rank p95 latency ≥5000ms opens an alert. Repeated
polls update evidence without duplicate alerts. Crossing below threshold resolves
it; disappearing/insufficient retained evidence closes it as `insufficient_data`,
not as recovery. Re-breaches create new alert records. No email/webhook is sent.
These are dashboard alerts with bounded recent evidence, not a paging system.
Head sampling can miss failures and bias small samples; metrics describe retained
producer-reported executions only. Old low-volume windows remain active until
retention expiry. Timing assumes a consistent producer clock.

Run `python scripts/benchmark_monitoring.py --count 100` against the local server.
The [recorded local measurement](docs/benchmarks/monitoring-local.json) used 100
sequential two-span submissions on macOS arm64: median instrumentation overhead
about **0.021ms**, median HTTP durable admission **2.15ms**, p95 **2.86ms**, zero
unaccepted spans in that run. All 106 demo/benchmark traces were subsequently
processed. This small local experiment measures admission separately from worker
completion; it does not establish production throughput or scalability.

## Real Groq agent: initial live validation

A bounded Groq integration is now implemented with local BM25 policy retrieval,
model-directed read-only tools, SDK traces, provider token usage, draft dev/holdout
cases and explicit comparison reports. **The live smoke test passed, and a paired
transient-timeout experiment showed the baseline failing while the grounded agent
recovered.** These small synthetic runs do not establish general model quality.

Start with `python scripts/run_groq_support.py --dry-run`, then follow the
[real-agent experiment guide](docs/REAL_AGENT_DEMO.md) for setup, recorded live results,
transient-failure recovery comparison and evaluation limits. No provider key is
needed for the normal CI test suite.

Live validation includes the initial boundary failure, two provider-error attempts,
and the passing runtime 1.2.0 regression and recovery comparison. See the
[recorded experiment evidence](docs/benchmarks/groq-live-validation.json); the subsequent
[frozen holdout evaluation](docs/benchmarks/HOLDOUT_REVIEW.md) passed all four
previously unrun cases in 12 provider requests. This small synthetic result does
not establish production accuracy; independent human label review remains pending.
