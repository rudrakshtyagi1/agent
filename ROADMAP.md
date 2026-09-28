# AgentGuard implementation roadmap

## Project thesis

AgentGuard tests and observes multi-step AI agents, identifies the first
observable failure with supporting trace evidence, and checks whether a fix
improves reliability. Inferred root causes must be labeled as hypotheses.

The placement demo: a support agent retrieves a refund policy, looks up an
order, and answers with citations. Inject an order API timeout or irrelevant
retrieval, inspect the trace, apply a fix, and compare both versions on the
same dataset. Keep a deterministic offline mode and a real model mode.

## Current state

Phases 1–3 are implemented: the FastAPI/database foundation now
executes the built-in offline support agent and persists nested spans with
completed/failed run status. The React trace explorer launches success and
simulated timeout scenarios and displays timing, inputs, outputs, and errors.

The tracer supports concurrent asyncio ancestry, duration measurement,
propagated errors, cancellation capture, and independent JSON snapshots.
API tests cover persistence across engine/application recreation, concurrent
execution protection, validation failures, and trace ownership checks.

Execution is request-scoped and bounded to 10 seconds. Status and spans commit
atomically; the intermediate running state is not exposed to other requests.
Process termination rolls back the transaction, leaving the original queued
run for an explicit retry. There is no durable background worker, live stream,
external trace-ingestion endpoint, OpenTelemetry export, or automatic redaction.
The demo uses fixture data and a template model; real LLM/RAG integrations and
general semantic evaluation are future work. Do not use the unauthenticated local API publicly.

Phase 3 adds ten evidence-backed metrics, frozen expectation snapshots,
idempotent persisted evaluations, and a versioned three-case diagnostic suite
with saved reports and per-metric denominators. Evaluation Studio opens case
traces and metric evidence. Groundedness is explicitly scoped to the support
refund template; simulated token usage is unavailable. This fixture dataset is
not a held-out benchmark. The next milestone is Phase 4 chaos testing.

## Build order and acceptance criteria

1. **Trace a working agent.** Connect the tracer to an executor and database;
   expose trace retrieval and build a timeline with parent-child relationships.
   A completed or failed run must retain its steps after server restart.
   Validate run/trace ownership and parent relationships on ingestion.
2. **Evaluate behavior.** Build a versioned support-agent dataset with expected
   tool calls, answers, citations, and relevant document IDs. Implement task
   success, tool correctness, retrieval recall/MRR, latency, and token usage.
   Report per-case evidence, aggregate denominators, and missing measurements.
3. **Test failure recovery.** Inject seeded timeouts, malformed tool results,
   missing documents, and irrelevant retrieval. Record the injection settings,
   retries, and recovery outcome. Bound retry budgets and execution time.
4. **Explain failures.** First use deterministic rules for observed exceptions,
   invalid tool arguments, and missing evidence. Add optional LLM diagnosis
   with cited span IDs, alternative explanations, and an unknown outcome.
   Measure diagnosis accuracy on labeled injected failures.
5. **Compare versions.** Run paired evaluations against the same cases; show
   regressions by slice and uncertainty in success-rate differences. Add a CI
   gate with explicit thresholds and machine-readable results. Record model,
   prompt, dataset, tool, and configuration versions.
6. **Monitor real runs.** Reuse ingestion for production traces, add background
   processing, bounded queues, sampling, retention, secret/PII filtering,
   authentication, tenant isolation, and alerts for meaningful changes.
   Measure ingestion overhead and dropped spans before claiming scalability.

## Architecture choices

Keep the existing Python/FastAPI and SQLAlchemy backend. Use SQLite for the
local demo and PostgreSQL for deployment. Build the existing React/TypeScript
frontend around real API results. Start with one worker and add Redis-backed
jobs only when execution needs to survive request/process lifetimes.

Keep instrumentation separate from evaluation: the target agent emits spans;
AgentGuard stores, evaluates, and diagnoses them. Evaluation failures must not
silently become agent failures. Capture explicit decisions and tool arguments,
not private chain-of-thought. Treat recorded text as untrusted data.

Replay should distinguish playback of recorded tool responses from re-running
live tools. Never promise exact reproduction of nondeterministic model calls.
LLM-as-judge scoring needs a rubric, judge version, human-labeled calibration
set, and disagreement reporting; it is not ground truth.

## Interview evidence to produce

- A reproducible success/failure/recovery demo with one-command setup.
- Tests for concurrent trace isolation, cancellation, retries, and persistence.
- A benchmark report comparing baseline and improved agents on held-out cases.
- Measured instrumentation overhead, latency distributions, and token usage.
- An architecture diagram and documented tradeoffs and known limitations.

Avoid adding many agent frameworks or autonomous investigator agents before
this complete workflow works. Depth comes from measured reliability and
defensible diagnosis, rather than the number of integrations.
