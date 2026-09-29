import { useEffect, useRef, useState } from "react";

type TraceRow = {
  id: string;
  trace_id: string;
  status: string;
  created_at: string;
  summary: null | {
    agent_name: string;
    agent_version: string;
    environment: string;
    execution_status: string;
    latency_ms: number;
    span_count: number;
    reported_tokens: number | null;
    observed_failure: { span_id: string; name: string } | null;
  };
};
type Overview = {
  tenant: string;
  auth_mode: string;
  counts: Record<string, number>;
  admission: {
    accepted: number;
    sampled_out: number;
    rejected: number;
    dropped_spans: number;
  };
  window: {
    samples: number;
    failure_rate: number | null;
    p95_latency_ms: number | null;
  };
  worker: { last_success: string | null; error: string | null };
  policy: {
    sample_rate: number;
    retention_days: number;
    capture_payloads: boolean;
    queue_capacity: number;
    window: number;
    min_samples: number;
    failure_rate: number;
    latency_ms: number;
  };
};
type Alert = {
  id: string;
  kind: string;
  status: string;
  created_at: string;
  evidence: {
    scope: string[];
    samples: number;
    failure_rate: number;
    p95_latency_ms: number;
    threshold: number;
    trace_ids: string[];
  };
};
type Detail = {
  id: string;
  status: string;
  payload: {
    agent_name: string;
    agent_version: string;
    status: string;
    spans: {
      id: string;
      parent_span_id: string | null;
      name: string;
      span_type: string;
      started_at: string;
      ended_at: string;
      error: string | null;
      input: unknown;
      output: unknown;
      metadata: unknown;
    }[];
  };
  summary: TraceRow["summary"];
};

export default function Monitoring() {
  const [key, setKey] = useState(""),
    [draft, setDraft] = useState(""),
    [overview, setOverview] = useState<Overview | null>(null),
    [traces, setTraces] = useState<TraceRow[]>([]),
    [alerts, setAlerts] = useState<Alert[]>([]),
    [detail, setDetail] = useState<Detail | null>(null),
    [error, setError] = useState(""),
    [updated, setUpdated] = useState(""),
    [paused, setPaused] = useState(false);
  const generation = useRef(0),
    selection = useRef(0);
  async function request<T>(path: string, token = key): Promise<T> {
    const response = await fetch(`/api/v1/monitoring${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok)
      throw new Error(
        response.status === 401
          ? "Enter a valid tenant monitoring key."
          : `Monitoring request failed (${response.status}).`,
      );
    return response.json();
  }
  useEffect(() => {
    setOverview(null);
    setTraces([]);
    setAlerts([]);
    setDetail(null);
    selection.current++;
  }, [key]);
  useEffect(() => {
    let active = true;
    const ticket = ++generation.current;
    let timeout: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const [o, t, a] = await Promise.all([
          request<Overview>("/overview", key),
          request<TraceRow[]>("/traces", key),
          request<Alert[]>("/alerts", key),
        ]);
        if (active && ticket === generation.current) {
          setOverview(o);
          setTraces(t);
          setAlerts(a);
          setError("");
          setUpdated(new Date().toLocaleTimeString());
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      } finally {
        if (active && !paused) timeout = setTimeout(refresh, 3000);
      }
    }
    refresh();
    return () => {
      active = false;
      clearTimeout(timeout);
    };
  }, [key, paused]);
  useEffect(() => {
    if (detail)
      document
        .getElementById("external-trace")
        ?.scrollIntoView({ behavior: "smooth" });
  }, [detail]);
  async function inspect(id: string) {
    const ticket = ++selection.current;
    setDetail(null);
    try {
      const value = await request<Detail>(`/traces/${id}`);
      if (ticket === selection.current) setDetail(value);
    } catch (e) {
      if (ticket === selection.current) setError((e as Error).message);
    }
  }
  return (
    <>
      <section className="heading">
        <div>
          <h1>Watch every execution.</h1>
          <p>
            External agent telemetry · durable processing · tenant-scoped alerts
          </p>
        </div>
        <button onClick={() => setPaused(!paused)}>
          {paused ? "Resume refresh" : "Pause refresh"}
        </button>
      </section>
      <section className="details">
        <div className="release-controls">
          <label>
            Tenant API key (optional in local demo)
            <input
              type="password"
              autoComplete="off"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
          </label>
          <div>
            <p>Kept only in this page’s memory. Each key selects its tenant.</p>
            <button
              onClick={() => {
                setKey(draft);
                setDraft("");
              }}
            >
              Connect tenant
            </button>{" "}
            <button
              onClick={() => {
                setKey("");
                setDraft("");
              }}
            >
              Clear key
            </button>
          </div>
        </div>
      </section>
      {error && (
        <div className="error" role="alert">
          {error} Displayed data may be stale.
        </div>
      )}
      {overview && (
        <>
          <p className="muted">
            Tenant: {overview.tenant} ·{" "}
            {overview.auth_mode === "local_demo"
              ? "Local demo — authentication disabled"
              : "Bearer authentication"}{" "}
            ·{" "}
            {paused
              ? "Refresh paused"
              : `Updated ${updated}; refreshes every 3 seconds`}
          </p>
          <section className="metrics">
            <div>
              <label>RECENT EXECUTIONS</label>
              <strong>{overview.window.samples}</strong>
              <small>Latest {overview.policy.window} processed traces</small>
            </div>
            <div>
              <label>EXECUTION FAILURE RATE</label>
              <strong>
                {overview.window.failure_rate === null
                  ? "—"
                  : `${(overview.window.failure_rate * 100).toFixed(1)}%`}
              </strong>
              <small>Not a task-quality score</small>
            </div>
            <div>
              <label>P95 LATENCY</label>
              <strong>
                {overview.window.p95_latency_ms?.toFixed(1) ?? "—"}
                <small> ms</small>
              </strong>
              <small>Agent-reported span timing</small>
            </div>
            <div>
              <label>QUEUED</label>
              <strong>{overview.counts.queued ?? 0}</strong>
              <small>
                {overview.counts.dead_letter ?? 0} processing failures
              </small>
            </div>
          </section>
          <section className="details">
            <h2>Pipeline health</h2>
            <p>
              {overview.worker.error ?? "Worker active"} · Last successful poll:{" "}
              {overview.worker.last_success
                ? new Date(overview.worker.last_success).toLocaleString()
                : "Not yet observed"}
            </p>
            <p>
              Accepted: {overview.admission.accepted} · Sampled-out submissions:{" "}
              {overview.admission.sampled_out} · Queue rejections:{" "}
              {overview.admission.rejected} · Spans omitted in these
              submissions: {overview.admission.dropped_spans}
            </p>
            <p>
              Sampling: {overview.policy.sample_rate * 100}% · Global pending
              limit: {overview.policy.queue_capacity} · Retention:{" "}
              {overview.policy.retention_days} days · Payload capture:{" "}
              {overview.policy.capture_payloads
                ? "Enabled with best-effort redaction"
                : "Off"}
            </p>
            <p className="muted">
              Alerts use the latest {overview.policy.window} retained executions
              per agent/version/environment, with at least{" "}
              {overview.policy.min_samples} samples. Thresholds: failure rate ≥{" "}
              {overview.policy.failure_rate * 100}% or p95 latency ≥{" "}
              {overview.policy.latency_ms} ms. Sampling can omit failures.
            </p>
          </section>
        </>
      )}
      <section className="details">
        <h2>Alert history</h2>
        {alerts.length === 0 ? (
          <p>
            No alerts in this tenant. Alerts appear once sufficient processed
            traces cross a threshold.
          </p>
        ) : (
          alerts.map((a) => (
            <div className="monitor-alert" key={a.id}>
              <b className={a.status === "open" ? "red" : "green"}>
                {a.status.replaceAll("_", " ")} · {a.kind.replaceAll("_", " ")}
              </b>
              <p>
                {a.evidence.scope.join(" / ")} · {a.evidence.samples} executions
                · {new Date(a.created_at).toLocaleString()}
              </p>
              <p>
                Failure rate: {(a.evidence.failure_rate * 100).toFixed(1)}% ·
                p95: {a.evidence.p95_latency_ms.toFixed(1)} ms
              </p>
              <button onClick={() => inspect(a.evidence.trace_ids[0])}>
                Inspect recent alert evidence
              </button>
            </div>
          ))
        )}
      </section>
      <div className="release-table">
        <table>
          <caption>Recent external traces (up to 50)</caption>
          <thead>
            <tr>
              <th>Agent / version</th>
              <th>Queue / execution</th>
              <th>Latency</th>
              <th>Observed error step</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {traces.map((t) => (
              <tr key={t.id}>
                <td>
                  {t.summary?.agent_name ?? t.trace_id.slice(0, 8)}
                  <small> {t.summary?.agent_version}</small>
                </td>
                <td>
                  {t.status} / {t.summary?.execution_status ?? "—"}
                </td>
                <td>{t.summary?.latency_ms ?? "—"} ms</td>
                <td>
                  {t.summary?.observed_failure?.name ?? "No recorded error"}
                </td>
                <td>
                  <button onClick={() => inspect(t.id)}>
                    Inspect {t.trace_id.slice(0, 8)}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {traces.length === 0 && (
          <p className="empty">
            No external traces yet. Send one with the Python SDK below.
          </p>
        )}
      </div>
      {detail && (
        <section className="details">
          <h2 id="external-trace">
            External trace: {detail.payload.agent_name}
          </h2>
          <p>
            {detail.payload.agent_version} · {detail.status} ·{" "}
            {detail.payload.status}
          </p>
          <p>
            Recorded errors describe observations, not proven root causes. Task
            correctness is not evaluated for unlabeled external traces.
          </p>
          {detail.payload.spans.map((s) => (
            <details key={s.id}>
              <summary>
                {s.error ? "×" : "✓"} {s.name} · {s.span_type}
              </summary>
              <pre>{JSON.stringify(s, null, 2)}</pre>
            </details>
          ))}
        </section>
      )}
      <section className="details">
        <h2>Connect a Python agent</h2>
        <p>
          Wrap existing retrieval, model and tool calls in spans. Export after
          the execution finishes. No external service credentials are needed for
          the local example.
        </p>
        <pre>{`PYTHONPATH=sdk python scripts/send_monitor_demo.py --count 6\n\nfrom agentguard import Trace\ntrace = Trace("my-agent", "1.0.0")\nwith trace.span("agent", "planner"):\n    with trace.span("lookup", "tool_call"):\n        result = your_existing_tool()\ntrace.export(api_key=os.getenv("AGENTGUARD_API_KEY"))`}</pre>
        <p>
          SDK exports completed traces with bounded retries. No streaming or
          automatic instrumentation. Capture is off by default; names must never
          contain secrets. Production requires HTTPS, configured keys and one
          API process.
        </p>
      </section>
    </>
  );
}
