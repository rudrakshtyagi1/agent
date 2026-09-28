"""Pure trace evaluators. Missing evidence is never converted into a pass."""
import json

from app.evaluation.contracts import EvaluationExpectations
from app.evaluation.retrieval.recall import recall
from app.evaluation.retrieval.mrr import reciprocal_rank
from app.evaluation.retrieval.ndcg import ndcg

VERSION = "agentguard-rules/1.0.0"


def evaluate(run, spans, case: dict) -> list[dict]:
    expectations = EvaluationExpectations.model_validate(case.get('metadata', {}).get('evaluation', {}))
    results = []
    def add(name, dimension, score=None, passed=None, reason='', evidence=(), **extra):
        results.append(dict(evaluator=name, dimension=dimension, score=score, passed=passed,
                            details={"evaluator_version": VERSION, "reason": reason,
                                     "availability": "measured" if score is not None or extra.get('value') is not None else "unavailable",
                                     "evidence_span_ids": [str(s.id) for s in evidence], **extra}))
    final_spans = [s for s in spans if s.span_type == 'final_response' and not s.error]
    final = final_spans[-1].output if final_spans else None
    final = final if isinstance(final, dict) else {}
    add('execution_success', 'system', float(run.status == 'completed'), run.status == 'completed',
        'Execution status; not a measure of answer correctness.', spans[:1])
    expected = expectations.expected_output
    if expected:
        # JSON comparison distinguishes true from 1 and compares nested structures exactly.
        mismatches = {key: {'expected': value, 'actual': final.get(key)} for key, value in expected.items()
                      if key not in final or json.dumps(final[key], sort_keys=True) != json.dumps(value, sort_keys=True)}
        passed = run.status == 'completed' and bool(final_spans) and not mismatches
        add('task_success', 'deterministic', float(passed), passed,
            'Completed execution plus exact match on the specified top-level output fields.', final_spans,
            mismatches=mismatches, expected_output=expected)
    else:
        add('task_success', 'deterministic', reason='No structured expected_output labels; natural-language expectations are not automatically judged.')
    tools = [s for s in spans if s.span_type == 'tool_call']
    expected_tools, forbidden = set(case.get('expected_tools', [])), set(case.get('forbidden_tools', []))
    actual_tools = {s.name for s in tools}
    if expected_tools or forbidden:
        missing, violations = sorted(expected_tools - actual_tools), sorted(forbidden & actual_tools)
        passed = not missing and not violations
        add('tool_correctness', 'deterministic', float(passed), passed,
            'Required tool presence and forbidden tool absence; does not validate arguments or tool success.', tools,
            missing_tools=missing, forbidden_calls=violations, actual_tools=sorted(actual_tools))
    else:
        add('tool_correctness', 'deterministic', reason='No required or forbidden tool labels.')
    retrievals = [s for s in spans if s.span_type == 'retrieval' and not s.error]
    ranking = []
    for s in retrievals:
        output = s.output or {}
        for doc in output.get('documents', []):
            if isinstance(doc, dict) and isinstance(doc.get('id'), str):
                ranking.append(doc['id'])
    ranking = list(dict.fromkeys(ranking))
    relevant = case.get('expected_documents', [])
    for name, metric in [('retrieval_recall', recall), ('retrieval_rr', reciprocal_rank), ('retrieval_ndcg', ndcg)]:
        score = metric(ranking, relevant)
        add(name, 'retrieval', score, None if score is None else score == 1,
            'Unique document ranking across retrieval spans in trace order; binary relevance.' if relevant else 'No relevant-document labels.',
            retrievals, retrieved=ranking, relevant=relevant)
    citations = final.get('citations')
    if final_spans and isinstance(citations, list) and citations:
        valid = sum(isinstance(c, str) and c in ranking for c in citations)
        score = valid / len(citations)
        add('citation_validity', 'deterministic', score, score == 1,
            'Cited IDs must occur in retrieved documents; this alone does not establish groundedness.', final_spans + retrievals)
    elif final_spans:
        add('citation_validity', 'deterministic', 0.0, False, 'Final answer contains no citations.', final_spans)
    else:
        add('citation_validity', 'deterministic', reason='No final answer to check.')
    # A deliberately narrow semantic check for the built-in refund agent.
    policy = 'Orders delivered within 30 days are eligible for a refund.'
    policy_found = any(d.get('id') == 'refund-policy-v1' and d.get('text') == policy
                       for s in retrievals for d in (s.output or {}).get('documents', []) if isinstance(d, dict))
    orders = [s for s in tools if s.name == 'lookup_order' and not s.error and isinstance(s.output, dict)]
    if final_spans and policy_found and orders and type(orders[-1].output.get('days_since_delivery')) in (int, float):
        order = orders[-1].output
        eligible = order['days_since_delivery'] <= 30
        answer = f"Order {order.get('order_id')} is {'eligible' if eligible else 'not eligible'} for a refund under the 30-day policy [refund-policy-v1]."
        passed = (final.get('eligible') is eligible and final.get('answer') == answer
                  and final.get('citations') == ['refund-policy-v1'])
        add('groundedness', 'semantic', float(passed), passed,
            'Support-template verifier: checks the entire fixed answer and eligibility against recorded policy and order age. Not a general semantic judge.',
            final_spans + retrievals + orders, scope='support-refund-template/v1')
    else:
        add('groundedness', 'semantic', reason='Requires a final answer, the recognized refund policy, and a successful order lookup.', scope='support-refund-template/v1')
    latency = run.total_latency_ms
    budget = expectations.max_latency_ms
    passed = latency <= budget if latency is not None and budget is not None else None
    add('latency', 'system', float(passed) if passed is not None else None, passed,
        'Measured run duration; pass/fail only when a latency budget is supplied.', spans[:1], value=latency, unit='ms', budget_ms=budget)
    models = [s for s in spans if s.span_type == 'model']
    usage = []
    for s in models:
        data = s.span_metadata.get('usage', {})
        if isinstance(data, dict) and not s.span_metadata.get('simulated'):
            counts = [data.get('input_tokens'), data.get('output_tokens')]
            if all(type(n) is int and n >= 0 for n in counts):
                usage.append(sum(counts))
    available = bool(models) and len(usage) == len(models)
    add('token_usage', 'system', reason='Sum of reported input/output tokens across all model calls; unavailable if any call lacks real usage.',
        evidence=models, value=sum(usage) if available else None, unit='tokens',
        measured_calls=len(usage), total_model_calls=len(models))
    return results


def aggregate(rows: list[dict]) -> dict:
    """Per-metric denominators; never average unlike dimensions into one score."""
    grouped = {}
    for row in rows:
        grouped.setdefault(row['evaluator'], []).append(row)
    output = {}
    for name, group in grouped.items():
        scores = [r['score'] for r in group if r['score'] is not None]
        judged = [r['passed'] for r in group if r['passed'] is not None]
        values = [r['details'].get('value') for r in group if r['details'].get('value') is not None]
        output[name] = {'total': len(group), 'scored': len(scores),
                        'unavailable': sum(r['details']['availability'] == 'unavailable' for r in group),
                        'mean_score': sum(scores)/len(scores) if scores else None,
                        'passed': sum(judged), 'judged': len(judged),
                        'mean_value': sum(values)/len(values) if values else None,
                        'unit': group[0]['details'].get('unit')}
    return output
