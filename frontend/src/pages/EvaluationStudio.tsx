import { useEffect, useState } from "react";
import { api, SuiteReport, MetricSummary } from "../services/api";

type SavedSuite = { id: string; dataset_version: string; created_at: string };
export default function EvaluationStudio({
  onRun,
}: {
  onRun: (id: string) => void;
}) {
  const [report, setReport] = useState<SuiteReport | null>(null);
  const [history, setHistory] = useState<SavedSuite[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    api<SavedSuite[]>("/evaluation-suites")
      .then(setHistory)
      .catch((e) => setError(e.message));
  }, []);
  async function launch() {
    setBusy(true);
    setError("");
    try {
      setReport(await api<SuiteReport>("/evaluation-suites/support-agent", {}));
      setHistory(await api<SavedSuite[]>("/evaluation-suites"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function load(id: string) {
    if (!id) return;
    setBusy(true);
    setError("");
    try {
      setReport(await api<SuiteReport>(`/evaluation-suites/${id}`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function score(m: MetricSummary) {
    return m.mean_value !== null
      ? `${m.mean_value.toFixed(1)} ${m.unit ?? ""}`
      : m.mean_score !== null
        ? `${(m.mean_score * 100).toFixed(1)}%`
        : "N/A";
  }
  return (
    <section className="studio">
      <div className="heading">
        <div>
          <h1>Measure the outcome.</h1>
          <p>
            Versioned cases. Explicit expectations. Evidence for every score.
          </p>
        </div>
        <button className="primary" disabled={busy} onClick={launch}>
          {busy ? "Working…" : "Run evaluation suite"}
        </button>
      </div>
      <div className="suite-intro">
        <b>Support refunds / v1.0.0</b>
        <p>
          Three diagnostic cases: eligible refund, outside the refund window,
          and a deliberate tool timeout. This small fixture suite demonstrates
          evaluation; it is not a held-out quality benchmark.
        </p>
        <select
          aria-label="Saved evaluation suite"
          disabled={busy}
          value={report?.id ?? ""}
          onChange={(e) => load(e.target.value)}
        >
          <option value="">Select a saved report</option>
          {history.map((s) => (
            <option value={s.id} key={s.id}>
              {new Date(s.created_at).toLocaleString()} · {s.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {report && (
        <>
          <p className="muted">
            {report.dataset_version} · {report.evaluator_version}
          </p>
          <div className="evaluation-grid">
            {Object.entries(report.summary).map(([name, m]) => (
              <div className="evaluation-card" key={name}>
                <label>{name.replaceAll("_", " ")}</label>
                <strong className="metric-score">{score(m)}</strong>
                <small>
                  {m.passed}/{m.judged} judged cases passed · {m.unavailable}/
                  {m.total} unavailable
                </small>
              </div>
            ))}
          </div>
          <h2 className="section-title">Case results</h2>
          <div className="suite-cases">
            {report.cases.map((c) => {
              const task = c.results.find(
                (r) => r.evaluator === "task_success",
              );
              return (
                <div className="case-row" key={c.run_id}>
                  <div>
                    <b>{c.name}</b>
                    <p>
                      Execution: {c.execution_status} · Task:{" "}
                      {task?.passed === true
                        ? "pass"
                        : task?.passed === false
                          ? "fail"
                          : "unavailable"}
                    </p>
                  </div>
                  <button onClick={() => onRun(c.run_id)}>
                    Inspect run ↗
                  </button>
                </div>
              );
            })}
          </div>
          <details className="report-details">
            <summary>Reproducibility details</summary>
            <p>Dataset SHA-256: {report.dataset_sha256}</p>
            <p>Suite ID: {report.id}</p>
            <p>
              Scores use each run’s frozen expectations. Retrieval metrics
              average per case; unavailable results never count as zero or as a
              pass.
            </p>
          </details>
        </>
      )}
    </section>
  );
}
