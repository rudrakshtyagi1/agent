import { useEffect, useState } from "react";
import { api } from "../services/api";

type Summary = {
  total: number;
  measured_pairs: number;
  baseline_passes: number;
  candidate_passes: number;
  regressions: number;
  improvements: number;
  uncertainty: {
    lower: number | null;
    upper: number | null;
    limitation: string;
  };
};
type Request = { baseline_version: string; candidate_version: string };
type Report = {
  id: string;
  request: Request;
  dataset_version: string;
  dataset_sha256: string;
  summary: Summary;
  slices: Record<string, Summary>;
  limitations: string[];
  gate: {
    status: string;
    checks: {
      name: string;
      actual: unknown;
      threshold: unknown;
      passed: boolean;
    }[];
  };
  cases: {
    case_id: string;
    name: string;
    change: string;
    baseline: { run_id: string };
    candidate: { run_id: string };
  }[];
};
type History = {
  id: string;
  created_at: string;
  request: Request;
  gate_status: string;
};
type Replay = {
  run_id: string;
  status: string;
  error: string | null;
  recorded_calls: number;
  consumed_calls: number;
  source_output: unknown;
  candidate_output: unknown;
  limitation: string;
};
export default function RegressionLab({
  onRun,
}: {
  onRun: (id: string) => void;
}) {
  const [versions, setVersions] = useState<
    Record<string, { description: string }>
  >({});
  const [baseline, setBaseline] = useState("1.0.0"),
    [candidate, setCandidate] = useState("1.1.0");
  const [budget, setBudget] = useState(0),
    [rate, setRate] = useState(1),
    [minimum, setMinimum] = useState(5),
    [latency, setLatency] = useState("");
  const [history, setHistory] = useState<History[]>([]),
    [report, setReport] = useState<Report | null>(null),
    [replay, setReplay] = useState<Replay | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    Promise.all([
      api<{ versions: typeof versions }>("/regressions/versions"),
      api<History[]>("/regressions/reports"),
    ])
      .then(([v, h]) => {
        setVersions(v.versions);
        setHistory(h);
      })
      .catch((e) => setError(e.message));
  }, []);
  async function compare() {
    setBusy(true);
    setError("");
    setReplay(null);
    try {
      setReport(
        await api<Report>("/regressions/compare", {
          baseline_version: baseline,
          candidate_version: candidate,
          gate: {
            max_regressions: budget,
            min_task_success_rate: rate,
            min_measured_cases: minimum,
            max_mean_latency_increase_ms:
              latency === "" ? null : Number(latency),
          },
        }),
      );
      setHistory(await api<History[]>("/regressions/reports"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function play(id: string) {
    if (!report) return;
    setBusy(true);
    setError("");
    setReplay(null);
    try {
      setReplay(
        await api<Replay>(`/runs/${id}/replay`, {
          candidate_version: report.request.candidate_version,
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <section className="heading">
        <div>
          <h1>Ship with evidence.</h1>
          <p>
            Compare executable versions on identical cases. Gate every release.
          </p>
        </div>
        <span className="badge">REGRESSION LAB</span>
      </section>
      <section className="details">
        <h2>Next comparison</h2>
        <div className="release-controls">
          <label>
            Baseline
            <select
              aria-label="Baseline version"
              value={baseline}
              onChange={(e) => setBaseline(e.target.value)}
            >
              {Object.entries(versions).map(([v, d]) => (
                <option key={v} value={v}>
                  {v} · {d.description}
                </option>
              ))}
            </select>
          </label>
          <label>
            Candidate
            <select
              aria-label="Candidate version"
              value={candidate}
              onChange={(e) => setCandidate(e.target.value)}
            >
              {Object.entries(versions).map(([v, d]) => (
                <option key={v} value={v}>
                  {v} · {d.description}
                </option>
              ))}
            </select>
          </label>
          <label>
            Allowed regressions
            <input
              type="number"
              min="0"
              max="100"
              value={budget}
              onChange={(e) => setBudget(Number(e.target.value))}
            />
          </label>
          <label>
            Minimum success rate (0–1)
            <input
              type="number"
              min="0"
              max="1"
              step="0.1"
              value={rate}
              onChange={(e) => setRate(Number(e.target.value))}
            />
          </label>
          <label>
            Minimum measured cases
            <input
              type="number"
              min="1"
              max="100"
              value={minimum}
              onChange={(e) => setMinimum(Number(e.target.value))}
            />
          </label>
          <label>
            Latency increase budget (ms, optional)
            <input
              type="number"
              min="0"
              value={latency}
              onChange={(e) => setLatency(e.target.value)}
            />
          </label>
        </div>
        <button className="primary" disabled={busy} onClick={compare}>
          {busy ? "Working…" : "Compare versions"}
        </button>
        <p className="muted">
          Five fixed support cases · ten executions · no external model calls.
          Missing required measurements block the gate.
        </p>
      </section>
      {error && (
        <div role="alert" className="error">
          {error}
        </div>
      )}
      <label className="release-history">
        Saved comparisons
        <select
          aria-label="Saved comparisons"
          disabled={busy}
          value={report?.id ?? ""}
          onChange={async (e) => {
            if (!e.target.value) return;
            setBusy(true);
            setReplay(null);
            try {
              setReport(
                await api<Report>(`/regressions/reports/${e.target.value}`),
              );
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <option value="">Select a report</option>
          {history.map((h) => (
            <option key={h.id} value={h.id}>
              {h.request.baseline_version} → {h.request.candidate_version} ·{" "}
              {h.gate_status} · {new Date(h.created_at).toLocaleString()}
            </option>
          ))}
        </select>
      </label>
      {report && (
        <>
          <section className="heading">
            <div>
              <h2>Release gate: {report.gate.status}</h2>
              <p>
                Saved report · {report.request.baseline_version} →{" "}
                {report.request.candidate_version}
              </p>
            </div>
          </section>
          <section className="metrics">
            <div>
              <label>BASELINE PASSES</label>
              <strong>
                {report.summary.baseline_passes}/{report.summary.measured_pairs}
              </strong>
            </div>
            <div>
              <label>CANDIDATE PASSES</label>
              <strong>
                {report.summary.candidate_passes}/
                {report.summary.measured_pairs}
              </strong>
            </div>
            <div>
              <label>REGRESSIONS</label>
              <strong className="red">{report.summary.regressions}</strong>
            </div>
            <div>
              <label>IMPROVEMENTS</label>
              <strong className="green">{report.summary.improvements}</strong>
            </div>
          </section>
          <div className="release-table">
            <table>
              <caption>Gate checks</caption>
              <thead>
                <tr>
                  <th>Check</th>
                  <th>Observed</th>
                  <th>Threshold</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {report.gate.checks.map((c) => (
                  <tr key={c.name}>
                    <td>{c.name.replaceAll("_", " ")}</td>
                    <td>{JSON.stringify(c.actual)}</td>
                    <td>{JSON.stringify(c.threshold)}</td>
                    <td className={c.passed ? "green" : "red"}>
                      {c.passed ? "Pass" : "Fail"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="release-table">
            <table>
              <caption>Case evidence</caption>
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Change</th>
                  <th>Inspect</th>
                  <th>Recorded playback</th>
                </tr>
              </thead>
              <tbody>
                {report.cases.map((c) => (
                  <tr key={c.case_id}>
                    <td>{c.name}</td>
                    <td>{c.change.replaceAll("_", " ")}</td>
                    <td>
                      <button onClick={() => onRun(c.baseline.run_id)}>
                        Baseline
                      </button>{" "}
                      <button onClick={() => onRun(c.candidate.run_id)}>
                        Candidate
                      </button>
                    </td>
                    <td>
                      <button
                        disabled={busy}
                        onClick={() => play(c.baseline.run_id)}
                      >
                        Replay {c.name}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {replay && (
            <section className="details">
              <h2>Recorded playback: {replay.status}</h2>
              <p>
                {replay.consumed_calls}/{replay.recorded_calls} recorded calls
                consumed. {replay.limitation}
              </p>
              {replay.error && <div className="error">{replay.error}</div>}
              <div className="payloads">
                <div>
                  <h3>Source output</h3>
                  <pre>{JSON.stringify(replay.source_output, null, 2)}</pre>
                </div>
                <div>
                  <h3>Candidate output</h3>
                  <pre>{JSON.stringify(replay.candidate_output, null, 2)}</pre>
                </div>
              </div>
              <button onClick={() => onRun(replay.run_id)}>
                Inspect replay trace
              </button>
            </section>
          )}
          <div className="release-table">
            <table>
              <caption>Slice outcomes (memberships overlap)</caption>
              <thead>
                <tr>
                  <th>Slice</th>
                  <th>Measured</th>
                  <th>Baseline passes</th>
                  <th>Candidate passes</th>
                  <th>Regressions</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(report.slices).map(([tag, s]) => (
                  <tr key={tag}>
                    <td>{tag}</td>
                    <td>
                      {s.measured_pairs}/{s.total}
                    </td>
                    <td>{s.baseline_passes}</td>
                    <td>{s.candidate_passes}</td>
                    <td>{s.regressions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <section className="details">
            <h2>Scope & reproducibility</h2>
            <p>
              Illustrative 95% paired Hoeffding interval:{" "}
              {report.summary.uncertainty.lower?.toFixed(2)} to{" "}
              {report.summary.uncertainty.upper?.toFixed(2)}.{" "}
              {report.summary.uncertainty.limitation}
            </p>
            {report.limitations.map((l) => (
              <p key={l}>{l}</p>
            ))}
            <p>{report.dataset_version}</p>
            <pre>Dataset SHA-256: {report.dataset_sha256}</pre>
            <details>
              <summary>Full saved report</summary>
              <pre>{JSON.stringify(report, null, 2)}</pre>
            </details>
          </section>
        </>
      )}
    </>
  );
}
