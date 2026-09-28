import { useEffect, useState } from "react";
import { api, Diagnosis } from "../services/api";

export default function DiagnosisPanel({
  runId,
  onEvidence,
}: {
  runId: string;
  onEvidence: (id: string) => void;
}) {
  const [report, setReport] = useState<Diagnosis | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<Diagnosis | null>(`/runs/${runId}/diagnosis`)
      .then((r) => {
        if (active) setReport(r);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [runId]);
  async function diagnose() {
    setBusy(true);
    setError("");
    try {
      setReport(await api<Diagnosis>(`/runs/${runId}/diagnose`, {}));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="diagnosis-panel">
      <div className="panel-title">
        <h2>Failure diagnosis</h2>
        <button disabled={busy || loading} onClick={diagnose}>
          {busy
            ? "Diagnosing…"
            : report
              ? "Load saved diagnosis"
              : "Diagnose run"}
        </button>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {loading ? (
        <p role="status">Loading diagnosis…</p>
      ) : (
        !report && (
          <p>
            Analyze this trace and its evaluation evidence. Unproven causes stay
            unknown.
          </p>
        )
      )}
      {report && (
        <>
          <div className="diagnosis-outcome">
            <b>{report.outcome.replaceAll("_", " ")}</b>
            <span>
              Task:{" "}
              {report.task_passed === null
                ? "unavailable"
                : report.task_passed
                  ? "passed"
                  : "failed"}
            </span>
          </div>
          {report.evaluation_note && (
            <p className="notice">
              Evaluation unavailable: {report.evaluation_note}
            </p>
          )}
          {report.findings.length === 0 && (
            <p>
              No observed errors or failed checks. This does not prove
              correctness.
            </p>
          )}
          {report.findings.map((f) => (
            <article className="finding" key={f.id}>
              <div className="panel-title">
                <h3>{f.title}</h3>
                <span className={f.status === "recovered" ? "green" : "red"}>
                  {f.status}
                </span>
              </div>
              <div className="finding-tags">
                <span>
                  {f.id === report.primary_finding_id
                    ? "Primary finding"
                    : f.role.replaceAll("_", " ")}
                </span>
                <span>{f.category.replaceAll("_", " ")}</span>
                <span>{f.evidence_level.replaceAll("_", " ")}</span>
              </div>
              <p>{f.explanation}</p>
              <p>
                <b>Component:</b> {f.component} · <b>Underlying cause:</b>{" "}
                {f.cause_status.replaceAll("_", " ")}
              </p>
              {f.injection_evidence.length > 0 && (
                <p className="notice">
                  Recorded synthetic injection is linked to this failing step.
                  It confirms the test intervention, not a real service root
                  cause.
                </p>
              )}
              <div className="evidence-links">
                {f.evidence_span_ids.map((id, i) => (
                  <button key={id} onClick={() => onEvidence(id)}>
                    Failure evidence {i + 1} ↗
                  </button>
                ))}
                {f.recovery_span_ids.map((id, i) => (
                  <button key={id} onClick={() => onEvidence(id)}>
                    Recovery evidence {i + 1} ↗
                  </button>
                ))}
              </div>
              <h4>Next checks</h4>
              <ul>
                {f.next_steps.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
              <details>
                <summary>Recorded observations & provenance</summary>
                <pre>
                  {JSON.stringify(
                    {
                      subtype: f.subtype,
                      observations: f.observations,
                      evaluation_ids: f.evaluation_ids,
                      injection_evidence: f.injection_evidence,
                      fingerprint: f.fingerprint,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
            </article>
          ))}
          <details className="report-details">
            <summary>Diagnosis scope · {report.diagnosis_version}</summary>
            <ul>
              {report.limitations.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </details>
        </>
      )}
    </section>
  );
}
