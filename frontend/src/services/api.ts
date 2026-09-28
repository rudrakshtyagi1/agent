export interface Run {
  id: string;
  status: string;
  agent_version: string;
  created_at: string;
  total_latency_ms: number | null;
  error: string | null;
}
export interface Span {
  id: string;
  parent_span_id: string | null;
  name: string;
  span_type: string;
  started_at: string;
  duration_ms: number | null;
  input: unknown;
  output: unknown;
  metadata: Record<string, unknown>;
  error: string | null;
}
export interface Trace {
  trace_id: string;
  run_id: string;
  spans: Span[];
}
export async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(
    `/api/v1${path}`,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      typeof error.error === "string"
        ? error.error
        : `Request failed (${response.status})`,
    );
  }
  return response.json();
}
export async function demoRun(scenario: string): Promise<Run> {
  type Agent = { id: string; name: string; version: string; endpoint: string };
  const name = "AgentGuard offline support";
  // Register using the unique name/version constraint, then locate an existing demo.
  const response = await fetch("/api/v1/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      version: "1.0.0",
      endpoint: "builtin://support",
      model: "deterministic-template",
    }),
  });
  let agent: Agent;
  if (response.ok) agent = await response.json();
  else if (response.status === 409) {
    const agents = await api<Agent[]>("/agents?limit=500");
    const existing = agents.find(
      (a) => a.name === name && a.version === "1.0.0",
    );
    if (!existing) throw new Error("Existing demo agent could not be found.");
    agent = existing;
  } else throw new Error("Could not register the demo agent.");
  const test = await api<{ id: string }>("/test-cases", {
    name:
      scenario === "success" ? "Refund eligibility" : "Order service timeout",
    category: "functional",
    expected_tools: ["lookup_order"],
    expected_documents: ["refund-policy-v1"],
    metadata: {
      evaluation: {
        expected_output: { eligible: true, citations: ["refund-policy-v1"] },
        max_latency_ms: 1000,
      },
    },
    input: {
      scenario,
      order_id: "ORD-1001",
      question: "Can I refund my order?",
    },
  });
  const run = await api<Run>("/runs", {
    agent_id: agent.id,
    agent_version: agent.version,
    test_case_id: test.id,
  });
  return api<Run>(`/runs/${run.id}/execute`, {});
}

export interface Evaluation {
  id: string;
  evaluator: string;
  dimension: string;
  score: number | null;
  passed: boolean | null;
  details: {
    reason: string;
    availability: string;
    evidence_span_ids: string[];
    value?: number | null;
    unit?: string;
    [key: string]: unknown;
  };
}
export interface MetricSummary {
  total: number;
  scored: number;
  unavailable: number;
  mean_score: number | null;
  passed: number;
  judged: number;
  mean_value: number | null;
  unit?: string;
}
export interface EvaluationReport {
  evaluator_version: string;
  results: Evaluation[];
  summary: Record<string, MetricSummary>;
}
export interface SuiteReport {
  id: string;
  dataset_version: string;
  dataset_sha256: string;
  dataset_description: string;
  evaluator_version: string;
  summary: Record<string, MetricSummary>;
  cases: (EvaluationReport & {
    name: string;
    run_id: string;
    execution_status: string;
  })[];
}

export interface ChaosRun {
  run_id: string;
  status: string;
  error: string | null;
  latency_ms: number;
  task_passed: boolean | null;
  injected_count: number;
  retry_count: number;
  attempts: Record<string, number>;
  fault_events: {
    span_id: string;
    kind: string;
    target: string;
    attempt: number;
    injected: boolean;
    draw: number;
  }[];
}
export interface ChaosReport {
  id: string;
  engine_version: string;
  runtime_version: string;
  config_sha256: string;
  config: {
    seed: number;
    probability: number;
    fail_first_attempts: number;
    retry: { max_attempts: number; backoff_ms: number };
    faults: string[];
    order_id: string;
  };
  baseline: ChaosRun;
  comparisons: {
    fault: string;
    unprotected: ChaosRun;
    protected: ChaosRun;
    recovered: boolean | null;
    retry_rescued_task: boolean;
    latency_delta_ms: number;
  }[];
  summary: {
    fault_types: number;
    injected_cases: number;
    not_injected_cases: number;
    recovered_cases: number;
    recovery_rate: number | null;
    retry_rescued_cases: number;
  };
  limitations: string;
}
