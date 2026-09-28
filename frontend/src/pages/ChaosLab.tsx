import { useEffect, useState } from "react";
import { api, ChaosReport, ChaosRun } from "../services/api";

const faults = [
  {
    id: "tool_timeout",
    label: "Tool timeout",
    text: "Order lookup raises a timeout.",
  },
  {
    id: "malformed_tool",
    label: "Malformed response",
    text: "Order age becomes invalid text.",
  },
  {
    id: "missing_documents",
    label: "Missing documents",
    text: "Retrieval returns no evidence.",
  },
  {
    id: "irrelevant_retrieval",
    label: "Irrelevant retrieval",
    text: "Shipping policy replaces refund policy.",
  },
];

export default function ChaosLab({ onRun }: { onRun: (id: string) => void }) {
  const [seed, setSeed] = useState(42);
  const [probability, setProbability] = useState(1);
  const [failFirst, setFailFirst] = useState(1);
  const [attempts, setAttempts] = useState(2);
  const [backoff, setBackoff] = useState(20);
  const [selected, setSelected] = useState(faults.map((f) => f.id));
  const [report, setReport] = useState<ChaosReport | null>(null);
  const [history, setHistory] = useState<{ id: string; created_at: string }[]>(
    [],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    api<typeof history>("/chaos/campaigns")
      .then(setHistory)
      .catch((e) => setError(e.message));
  }, []);
  async function launch(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      setReport(
        await api<ChaosReport>("/chaos/campaigns", {
          seed,
          probability,
          fail_first_attempts: failFirst,
          retry: { max_attempts: attempts, backoff_ms: backoff },
          faults: selected,
          order_id: "ORD-1001",
        }),
      );
      setHistory(await api<typeof history>("/chaos/campaigns"));
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
      setReport(await api<ChaosReport>(`/chaos/campaigns/${id}`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function runCell(run: ChaosRun, label: string) {
    return (
      <div className="chaos-run">
        <label>{label}</label>
        <strong className={run.task_passed ? "green" : "red"}>
          {run.task_passed ? "Task passed" : "Task failed"}
        </strong>
        <small>
          {run.latency_ms} ms · {run.injected_count} injected ·{" "}
          {run.retry_count} retries
        </small>
        <button onClick={() => onRun(run.run_id)}>
          Inspect {label.toLowerCase()} ↗
        </button>
      </div>
    );
  }
  return (
    <section className="chaos-lab">
      <div className="heading">
        <div>
          <h1>Break it. Measure recovery.</h1>
          <p>Controlled faults. Paired runs. Every retry in the trace.</p>
        </div>
        <span className="badge">LOCAL FIXTURES ONLY</span>
      </div>
      <form onSubmit={launch} className="chaos-config">
        <fieldset disabled={busy}>
          <legend>Configure a campaign</legend>
          <div className="fault-options">
            {faults.map((f) => (
              <label className="fault-option" key={f.id}>
                <input
                  type="checkbox"
                  checked={selected.includes(f.id)}
                  onChange={(e) =>
                    setSelected(
                      e.target.checked
                        ? [...selected, f.id]
                        : selected.filter((v) => v !== f.id),
                    )
                  }
                />
                <span>
                  <b>{f.label}</b>
                  <small>{f.text}</small>
                </span>
              </label>
            ))}
          </div>
          <div className="chaos-fields">
            <label>
              Seed
              <input
                aria-label="Seed"
                type="number"
                min="0"
                max="4294967295"
                required
                value={seed}
                onChange={(e) => setSeed(e.target.valueAsNumber)}
              />
            </label>
            <label>
              Injection probability
              <input
                aria-label="Injection probability"
                type="number"
                min="0"
                max="1"
                step="0.1"
                required
                value={probability}
                onChange={(e) => setProbability(e.target.valueAsNumber)}
              />
            </label>
            <label>
              Fault-eligible attempts
              <input
                aria-label="Fault-eligible attempts"
                type="number"
                min="1"
                max="3"
                required
                value={failFirst}
                onChange={(e) => setFailFirst(e.target.valueAsNumber)}
              />
            </label>
            <label>
              Max attempts (including first)
              <input
                aria-label="Max attempts"
                type="number"
                min="1"
                max="3"
                required
                value={attempts}
                onChange={(e) => setAttempts(e.target.valueAsNumber)}
              />
            </label>
            <label>
              Base backoff (ms)
              <input
                aria-label="Base backoff"
                type="number"
                min="0"
                max="200"
                required
                value={backoff}
                onChange={(e) => setBackoff(e.target.valueAsNumber)}
              />
            </label>
          </div>
          <p>
            Default: one transient fault per type, then a clean retry. Set
            fault-eligible attempts to 3 to test exhaustion. Probability 0 tests
            the no-injection control.
          </p>
          <button className="primary" disabled={busy || !selected.length}>
            {busy ? "Running campaign…" : "Run chaos campaign"}
          </button>
        </fieldset>
      </form>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <div className="saved-campaign">
        <label htmlFor="chaos-history">Saved campaigns</label>
        <select
          id="chaos-history"
          disabled={busy}
          value={report?.id ?? ""}
          onChange={(e) => load(e.target.value)}
        >
          <option value="">Select a report</option>
          {history.map((h) => (
            <option key={h.id} value={h.id}>
              {new Date(h.created_at).toLocaleString()} · {h.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </div>
      {report && (
        <>
          <div className="report-banner">
            <b>Report configuration</b>
            <p>
              Seed {report.config.seed} · probability{" "}
              {report.config.probability} · first{" "}
              {report.config.fail_first_attempts} attempts eligible · max{" "}
              {report.config.retry.max_attempts} attempts ·{" "}
              {report.config.retry.backoff_ms} ms base backoff
            </p>
            <small>
              Configuration above is for the next campaign. These results use
              the saved settings shown here.
            </small>
          </div>
          <div className="metrics">
            <div>
              <label>RECOVERY RATE</label>
              <strong>
                {report.summary.recovery_rate === null
                  ? "N/A"
                  : `${Math.round(report.summary.recovery_rate * 100)}%`}
              </strong>
              <small>
                {report.summary.recovered_cases}/{report.summary.injected_cases}{" "}
                injected retry runs passed
              </small>
            </div>
            <div>
              <label>RESCUED BY RETRIES</label>
              <strong>{report.summary.retry_rescued_cases}</strong>
              <small>Failed without retries, passed with them</small>
            </div>
            <div>
              <label>NOT INJECTED</label>
              <strong>{report.summary.not_injected_cases}</strong>
              <small>Excluded from recovery denominator</small>
            </div>
            <div>
              <label>BASELINE</label>
              <strong className="mode">
                {report.baseline.task_passed ? "Passed" : "Failed"}
              </strong>
              <small>
                {report.baseline.latency_ms} ms · no injected faults
              </small>
              <button onClick={() => onRun(report.baseline.run_id)}>
                Inspect baseline ↗
              </button>
            </div>
          </div>
          <div className="chaos-comparisons">
            {report.comparisons.map((c) => (
              <article className="chaos-comparison" key={c.fault}>
                <div className="panel-title">
                  <h2>{faults.find((f) => f.id === c.fault)?.label}</h2>
                  <span
                    className={
                      c.recovered === null
                        ? "muted"
                        : c.recovered
                          ? "green"
                          : "red"
                    }
                  >
                    {c.recovered === null
                      ? "No fault fired"
                      : c.recovered
                        ? "Recovered"
                        : "Not recovered"}
                  </span>
                </div>
                <div className="paired-runs">
                  {runCell(c.unprotected, "Without retries")}
                  {runCell(c.protected, "With retries")}
                </div>
                <p>
                  Retry-run latency vs baseline:{" "}
                  {c.latency_delta_ms >= 0 ? "+" : ""}
                  {c.latency_delta_ms} ms. Timing varies between executions.
                </p>
                <details>
                  <summary>Injection decisions & attempts</summary>
                  <pre>
                    {JSON.stringify(
                      {
                        attempts: c.protected.attempts,
                        decisions: c.protected.fault_events,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </article>
            ))}
          </div>
          <details className="report-details">
            <summary>Reproducibility & scope</summary>
            <p>{report.limitations}</p>
            <p>
              {report.engine_version} · {report.runtime_version}
            </p>
            <p>Config SHA-256: {report.config_sha256}</p>
          </details>
        </>
      )}
    </section>
  );
}
