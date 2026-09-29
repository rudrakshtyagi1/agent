import { useEffect, useRef, useState } from "react";
import { api, demoRun, Run, Span, Trace } from "./services/api";

import EvaluationPanel from "./components/EvaluationPanel";
import EvaluationStudio from "./pages/EvaluationStudio";
import ChaosLab from "./pages/ChaosLab";
import RegressionLab from "./pages/RegressionLab";
import FailureLab from "./pages/FailureLab";
import DiagnosisPanel from "./components/DiagnosisPanel";

export default function App() {
  const [page, setPage] = useState("traces");
  const [runs, setRuns] = useState<Run[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [trace, setTrace] = useState<Trace | null>(null);
  const [span, setSpan] = useState<Span | null>(null);
  const [filter, setFilter] = useState("all");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const selection = useRef(0);
  async function refresh() {
    setRuns(await api<Run[]>("/runs?limit=100"));
  }
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, []);
  async function select(next: Run, evidenceId?: string) {
    const ticket = ++selection.current;
    setRun(next);
    setTrace(null);
    setSpan(null);
    setError("");
    if (next.status === "queued" || next.status === "running") {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const result = await api<Trace>(`/runs/${next.id}/trace`);
      if (ticket !== selection.current) return;
      setTrace(result);
      setSpan(
        result.spans.find((s) => s.id === evidenceId) ??
          result.spans.find(
            (s) =>
              s.error &&
              !result.spans.some(
                (child) => child.parent_span_id === s.id && child.error,
              ),
          ) ??
          result.spans[0],
      );
    } catch (e) {
      if (ticket === selection.current) setError((e as Error).message);
    } finally {
      if (ticket === selection.current) setLoading(false);
    }
  }
  async function launch(scenario: string) {
    setBusy(true);
    setError("");
    try {
      const next = await demoRun(scenario);
      await refresh();
      await select(next);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function executeSelected() {
    if (!run) return;
    setBusy(true);
    setError("");
    try {
      const next = await api<Run>(`/runs/${run.id}/execute`, {});
      await refresh();
      await select(next);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function inspectRun(id: string, evidenceId?: string) {
    try {
      const selected = await api<Run>(`/runs/${id}`);
      await refresh();
      setPage("traces");
      await select(selected, evidenceId);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const shown = runs.filter((r) => filter === "all" || r.status === filter);
  const total = trace?.spans[0]?.duration_ms || 1;
  const start = trace ? Date.parse(trace.spans[0].started_at) : 0;
  function depth(s: Span): number {
    let level = 0,
      parent = s.parent_span_id;
    const visited = new Set<string>();
    while (parent && trace && !visited.has(parent)) {
      visited.add(parent);
      level++;
      parent = trace.spans.find((p) => p.id === parent)?.parent_span_id ?? null;
    }
    return level;
  }
  return (
    <div className="shell">
      <aside className="sidebar">
        <a className="brand" href="/">
          ◈ <span>AgentGuard</span>
        </a>
        <div className="workspace">ENGINEERING WORKSPACE</div>
        <button
          className={`nav ${page === "traces" ? "active" : ""}`}
          onClick={() => setPage("traces")}
        >
          ⌁ &nbsp; Trace explorer
        </button>
        <button
          className={`nav ${page === "evaluations" ? "active" : ""}`}
          onClick={() => setPage("evaluations")}
        >
          ◎ &nbsp; Evaluation studio
        </button>
        <button
          className={`nav ${page === "chaos" ? "active" : ""}`}
          onClick={() => setPage("chaos")}
        >
          ϟ &nbsp; Chaos lab
        </button>
        <button
          className={`nav ${page === "failures" ? "active" : ""}`}
          onClick={() => setPage("failures")}
        >
          ⌕ &nbsp; Failure lab
        </button>
        <button
          className={`nav ${page === "regressions" ? "active" : ""}`}
          onClick={() => setPage("regressions")}
        >
          ⇄ &nbsp; Regression lab
        </button>
        <div className="sidebar-note">
          <span className="dot" /> Local development
          <br />
          <small>Phase 06 · Release confidence</small>
        </div>
      </aside>
      <main>
        <header>
          <div className="eyebrow">OBSERVABILITY / EXECUTIONS</div>
          <span className="badge">OFFLINE DEMO</span>
        </header>
        <div className="mobile-nav">
          <button onClick={() => setPage("traces")}>Traces</button>
          <button onClick={() => setPage("evaluations")}>Evaluations</button>
          <button onClick={() => setPage("chaos")}>Chaos lab</button>
          <button onClick={() => setPage("failures")}>Failure lab</button>
          <button onClick={() => setPage("regressions")}>Regression lab</button>
        </div>
        {page !== "traces" && error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {page === "regressions" ? (
          <RegressionLab onRun={inspectRun} />
        ) : page === "failures" ? (
          <FailureLab onRun={inspectRun} />
        ) : page === "chaos" ? (
          <ChaosLab onRun={inspectRun} />
        ) : page === "evaluations" ? (
          <EvaluationStudio onRun={inspectRun} />
        ) : (
          <>
            <section className="heading">
              <div>
                <h1>Every step. In sight.</h1>
                <p>Follow an agent’s execution from input to outcome.</p>
              </div>
              <div className="actions">
                <button disabled={busy} onClick={() => launch("tool_timeout")}>
                  Simulate failure
                </button>
                <button
                  className="primary"
                  disabled={busy}
                  onClick={() => launch("success")}
                >
                  {busy ? "Executing…" : "↗ Run support agent"}
                </button>
              </div>
            </section>
            {error && (
              <div className="error" role="alert">
                {error}
              </div>
            )}
            <section className="metrics">
              <div>
                <label>LOADED RUNS</label>
                <strong>{runs.length}</strong>
                <small>Most recent 100</small>
              </div>
              <div>
                <label>COMPLETED</label>
                <strong>
                  {runs.filter((r) => r.status === "completed").length}
                </strong>
                <small>Execution finished</small>
              </div>
              <div>
                <label>FAILED</label>
                <strong className="red">
                  {runs.filter((r) => r.status === "failed").length}
                </strong>
                <small>Inspect the failing step</small>
              </div>
              <div>
                <label>EXECUTION MODE</label>
                <strong className="mode">Deterministic</strong>
                <small>Fixture tools · simulated model</small>
              </div>
            </section>
            <section className="explorer">
              <div className="run-list">
                <div className="panel-title">
                  <h2>Executions</h2>
                  <button
                    aria-label="Refresh runs"
                    onClick={() => refresh().catch((e) => setError(e.message))}
                  >
                    ↻
                  </button>
                </div>
                <select
                  aria-label="Filter run status"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                >
                  {["all", "completed", "failed", "queued", "running"].map(
                    (v) => (
                      <option key={v} value={v}>
                        {v === "all" ? "All statuses" : v}
                      </option>
                    ),
                  )}
                </select>
                {shown.length === 0 && (
                  <p className="empty">
                    No runs yet. Run the support agent to capture your first
                    trace.
                  </p>
                )}
                {shown.map((r) => (
                  <button
                    className={`run ${run?.id === r.id ? "selected" : ""}`}
                    key={r.id}
                    onClick={() => select(r)}
                  >
                    <div>
                      <span className={`status ${r.status}`}>{r.status}</span>
                      <small>{r.total_latency_ms ?? "—"} ms</small>
                    </div>
                    <b>{r.id.slice(0, 8)}</b>
                    <small>{new Date(r.created_at).toLocaleString()}</small>
                  </button>
                ))}
              </div>
              <div className="trace-panel">
                <div className="panel-title">
                  <h2>Execution trace</h2>
                  <span className="muted">
                    {trace
                      ? `${trace.spans.length} spans · ${total} ms`
                      : "Select a run"}
                  </span>
                </div>
                {!run && (
                  <div className="welcome">
                    <div className="trace-icon">⌁</div>
                    <h3>Your agent’s story starts here</h3>
                    <p>
                      Run a successful request or simulate a tool timeout.
                      <br />
                      Select any step to inspect its evidence.
                    </p>
                  </div>
                )}
                {loading && (
                  <p className="empty" role="status">
                    Loading persisted trace…
                  </p>
                )}
                {run?.status === "queued" && (
                  <div className="empty">
                    <p>This run is queued.</p>
                    <button disabled={busy} onClick={executeSelected}>
                      Execute run
                    </button>
                  </div>
                )}
                {run?.status === "running" && (
                  <p className="empty">
                    This run is executing. Refresh to check its status.
                  </p>
                )}
                {trace && (
                  <>
                    <div className="trace-id">TRACE {trace.trace_id}</div>
                    <div className="timeline-label">
                      <span>STEP / TYPE</span>
                      <span>RELATIVE TIMING</span>
                    </div>
                    {trace.spans.map((s) => (
                      <button
                        key={s.id}
                        className={`span-row ${span?.id === s.id ? "chosen" : ""}`}
                        onClick={() => setSpan(s)}
                      >
                        <div style={{ paddingLeft: depth(s) * 16 }}>
                          <b>
                            <span className={s.error ? "red" : "green"}>
                              {s.error ? "×" : "✓"}
                            </span>{" "}
                            {s.name}
                          </b>
                          <small>{s.span_type}</small>
                        </div>
                        <div className="timing">
                          <div className="track">
                            <i
                              className={s.error ? "bad" : ""}
                              style={{
                                marginLeft: `${Math.min(98, Math.max(0, ((Date.parse(s.started_at) - start) / total) * 100))}%`,
                                width: `${Math.max(1, Math.min(100, ((s.duration_ms ?? 0) / total) * 100))}%`,
                              }}
                            />
                          </div>
                          <small>{s.duration_ms} ms</small>
                        </div>
                      </button>
                    ))}
                  </>
                )}
                {trace && run && (
                  <EvaluationPanel
                    key={run.id}
                    runId={run.id}
                    onEvidence={(id) => {
                      const selected = trace.spans.find((s) => s.id === id);
                      if (selected) {
                        setSpan(selected);
                        document
                          .getElementById("span-details")
                          ?.scrollIntoView({ behavior: "smooth" });
                      }
                    }}
                  />
                )}
                {trace && run && (
                  <DiagnosisPanel
                    key={`diagnosis-${run.id}`}
                    runId={run.id}
                    onEvidence={(id) => {
                      const match = trace.spans.find((s) => s.id === id);
                      if (match) {
                        setSpan(match);
                        document
                          .getElementById("span-details")
                          ?.scrollIntoView({ behavior: "smooth" });
                      }
                    }}
                  />
                )}
                {span && (
                  <div className="details" id="span-details">
                    <div className="panel-title">
                      <h2>{span.name}</h2>
                      <span className="badge">SPAN DETAILS</span>
                    </div>
                    {span.error && (
                      <div className="error">
                        <b>Observed error</b>
                        <br />
                        {span.error}
                      </div>
                    )}
                    <div className="payloads">
                      <div>
                        <h3>Input</h3>
                        <pre>
                          {JSON.stringify(span.input, null, 2) ??
                            "Not recorded"}
                        </pre>
                      </div>
                      <div>
                        <h3>Output</h3>
                        <pre>
                          {JSON.stringify(span.output, null, 2) ??
                            "Not recorded"}
                        </pre>
                      </div>
                    </div>
                    <h3>Metadata</h3>
                    <pre>{JSON.stringify(span.metadata, null, 2)}</pre>
                  </div>
                )}
              </div>
            </section>
          </>
        )}
        <footer>
          Stored traces survive server restarts. Demo responses are generated
          from templates; no LLM is called.
        </footer>
      </main>
    </div>
  );
}
