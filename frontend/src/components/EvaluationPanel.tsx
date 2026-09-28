import { useEffect, useState } from "react";
import { api, EvaluationReport } from "../services/api";

export default function EvaluationPanel({
  runId,
  onEvidence,
}: {
  runId: string;
  onEvidence: (id: string) => void;
}) {
  const [report, setReport] = useState<EvaluationReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<EvaluationReport>(`/runs/${runId}/evaluations`)
      .then((r) => {
        if (active) setReport(r);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [runId]);
  async function evaluate() {
    setBusy(true);
    setError("");
    try {
      setReport(await api<EvaluationReport>(`/runs/${runId}/evaluate`, {}));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="evaluation-panel">
      <div className="panel-title">
        <h2>Evaluation results</h2>
        <button disabled={busy} onClick={evaluate}>
          {busy
            ? "Evaluating…"
            : report?.results.length
              ? "Load saved evaluation"
              : "Evaluate run"}
        </button>
      </div>
      <p>
        Execution completion and answer correctness are measured separately.
      </p>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {!report?.results.length && !error && (
        <p>
          No saved evaluation. Evaluate this run against its recorded
          expectations.
        </p>
      )}
      <div className="evaluation-grid">
        {report?.results.map((r) => (
          <details className="evaluation-card" key={r.id}>
            <summary>
              <span>{r.evaluator.replaceAll("_", " ")}</span>
              <strong
                className={
                  r.passed === false ? "red" : r.passed ? "green" : "muted"
                }
              >
                {r.details.availability === "unavailable"
                  ? "N/A"
                  : r.details.value != null
                    ? `${r.details.value} ${r.details.unit ?? ""}`
                    : `${Math.round((r.score ?? 0) * 100)}%`}
              </strong>
              <small>
                {r.passed === null
                  ? "No pass/fail verdict"
                  : r.passed
                    ? "Pass"
                    : "Fail"}
              </small>
            </summary>
            <p>{r.details.reason}</p>
            <div className="evidence-links">
              {r.details.evidence_span_ids.map((id, i) => (
                <button key={id} onClick={() => onEvidence(id)}>
                  Evidence {i + 1} ↗
                </button>
              ))}
            </div>
            <pre>{JSON.stringify(r.details, null, 2)}</pre>
          </details>
        ))}
      </div>
      {report?.results.length ? (
        <small className="muted">
          Evaluator {report.evaluator_version} · N/A metrics are excluded from
          averages.
        </small>
      ) : null}
    </section>
  );
}
