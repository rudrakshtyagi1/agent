# AgentGuard

AgentGuard is a comprehensive evaluation, reliability, chaos testing, and observability platform for AI agents.

Work in progress: see [the implementation roadmap](ROADMAP.md) for implemented
capabilities, planned milestones, and the placement demo.

## Tracing demo

After installing `backend/requirements.txt`, run from the repository root:

```sh
PYTHONPATH=backend python3 scripts/demo_trace.py
make test
```

The offline demo prints nested retrieval/tool spans and a simulated tool timeout
as JSON. No model API key is needed. Trace storage and the dashboard are not yet
connected to this tracer.

## Project Structure

```
agentguard/
├── backend/                  # FastAPI backend, evaluation engine, runtime, and intelligence
├── frontend/                 # Vite + React UI dashboard for evaluations, traces, and chaos testing
├── target_agents/            # Target agents under test (e.g. support_agent)
├── evals/                    # Test suites, golden datasets, and benchmarks
├── infrastructure/           # Docker, DB, Redis, and Qdrant configurations
├── scripts/                  # Seed, benchmark, and test generation scripts
└── .github/workflows/        # CI/CD workflows
```
