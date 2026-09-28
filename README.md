# AgentGuard

AgentGuard is a testing and observability platform for multi-step AI agents.
Phase 2 delivers an executable offline support agent, persisted nested traces,
and a React trace explorer. Evaluation, chaos campaigns, diagnosis, and live
monitoring follow in later phases; see [ROADMAP.md](ROADMAP.md).

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
