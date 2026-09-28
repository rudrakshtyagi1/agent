import { useEffect, useState } from "react";
import {
  api,
  Diagnosis,
  FailureGroups,
  DiagnosisBenchmark,
} from "../services/api";
import DiagnosisPanel from "../components/DiagnosisPanel";

export default function FailureLab({
  onRun,
}: {
  onRun: (runId: string, spanId?: string) => void;
}) {
  const [groups, setGroups] = useState<FailureGroups | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [benchmark, setBenchmark] = useState<DiagnosisBenchmark | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => {
    Promise.all([
      api<FailureGroups>("/failures/groups"),
      api<DiagnosisBenchmark | null>("/failures/benchmarks/latest"),
    ])
      .then(([g, b]) => {
        setGroups(g);
        setBenchmark(b);
      })
      .catch((e) => setError(e.message));
  }, []);
  async function analyze() {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ analyzed: number; reports: Diagnosis[] }>(
        "/failures/analyze-recent?limit=20",
        {},
      );
      setGroups(await api<FailureGroups>("/failures/groups"));
      setMessage(
        `Analyzed ${result.analyzed} recent completed or failed runs.`,
      );
      const first = result.reports.find((r) => r.findings.length);
      if (first) setSelected(first.run_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function audit() {
    setBusy(true);
    setError("");
    try {
      const result = await api<DiagnosisBenchmark>("/failures/benchmark", {});
      setBenchmark(result);
      setGroups(await api<FailureGroups>("/failures/groups"));
      setMessage(
        "Created nine fixture runs and checked their blinded diagnoses.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="failure-lab">
      <div className="heading">
        <div>
          <h1>Find the failing step.</h1>
          <p>
            Observed symptoms, supporting evidence, and the next useful check.
          </p>
        </div>
        <div className="actions">
          <button disabled={busy} onClick={audit}>
            Run diagnosis audit
          </button>
          <button className="primary" disabled={busy} onClick={analyze}>
            {busy ? "Analyzing…" : "Analyze recent runs"}
          </button>
        </div>
      </div>
      <div className="suite-intro">
        <b>Evidence first. Unknown when unproven.</b>
        <p>
          Analyze the latest 20 finished runs, including recovered and
          completed-but-incorrect runs. Similarity groups match symptom,
          component, and subtype; they do not establish a shared root cause.
        </p>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {message && <p role="status">{message}</p>}
      {benchmark && (
        <details className="audit-summary">
          <summary>
            Fixture audit: {benchmark.correct}/{benchmark.total} diagnoses
            matched
          </summary>
          <p>{benchmark.blind_inputs}</p>
          <p>{benchmark.limitations}</p>
          <div className="audit-cases">
            {benchmark.samples.map((s) => (
              <button key={s.run_id} onClick={() => setSelected(s.run_id)}>
                <b className={s.correct ? "green" : "red"}>
                  {s.correct ? "✓" : "×"}{" "}
                  {s.expected_subtype ?? "clean control"}
                </b>
                <small>
                  Expected {s.expected_outcome} · observed {s.predicted_outcome}
                  <br />
                  Predicted symptom: {s.predicted_subtype ?? "none"}
                </small>
              </button>
            ))}
          </div>
        </details>
      )}
      <h2 className="section-title">Similar failure groups</h2>
      <p className="muted">
        {groups?.window ?? "Loading groups…"} · {groups?.records_scanned ?? 0}{" "}
        records scanned
      </p>
      {groups?.groups.length === 0 && (
        <p>
          No diagnosed failures yet. Analyze recent runs or run the fixture
          audit.
        </p>
      )}
      <div className="failure-groups">
        {groups?.groups.map((g) => (
          <details key={g.fingerprint} className="failure-group">
            <summary>
              <b>{g.title}</b>
              <span>
                {g.occurrences} occurrences · {g.recovered} recovered
              </span>
            </summary>
            <p>
              {g.component} · {g.subtype}
            </p>
            <div className="evidence-links">
              {g.runs.map((r) => (
                <button
                  key={r.failure_id}
                  onClick={() => setSelected(r.run_id)}
                >
                  {r.run_id.slice(0, 8)} · {r.status}
                </button>
              ))}
            </div>
          </details>
        ))}
      </div>
      {selected && (
        <div className="selected-diagnosis">
          <div className="panel-title">
            <h2>Run {selected.slice(0, 8)}</h2>
            <button onClick={() => onRun(selected)}>Open trace ↗</button>
          </div>
          <DiagnosisPanel
            key={selected}
            runId={selected}
            onEvidence={(id) => onRun(selected, id)}
          />
        </div>
      )}
    </section>
  );
}
