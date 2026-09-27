# AgentGuard

AgentGuard is a comprehensive evaluation, reliability, chaos testing, and observability platform for AI agents.

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
