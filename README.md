# AgentGuard

AgentGuard is a testing and observability platform for multi-step AI agents.
Phase 3 includes an executable offline support agent, persisted nested traces,
a React trace explorer, and a versioned evaluation engine and suite dashboard.
Chaos campaigns, diagnosis, and live monitoring follow in later phases; see [ROADMAP.md](ROADMAP.md).

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
