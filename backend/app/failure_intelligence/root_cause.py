"""Evidence-based diagnosis with explicit unknowns and bounded causal claims."""
from app.failure_intelligence.feature_extractor import error_origins
from app.failure_intelligence.classifier import classify
from app.failure_intelligence.clustering import fingerprint

VERSION = 'agentguard-diagnosis/1.0.0'
GUIDANCE = {
    'tool_timeout': ('The tool boundary reported a timeout. The trace alone cannot distinguish network delay, service overload, or a client timeout setting.', ['Inspect the tool service and client timeout logs.', 'Keep retries bounded and use idempotency for side-effecting tools.']),
    'malformed_tool': ('The response violates the order schema. The upstream reason for the malformed payload is unknown.', ['Validate tool payloads before using them.', 'Check the producer schema and retain the failing payload.']),
    'missing_documents': ('No documents were returned. Index coverage, filters, and retrieval availability are possible causes, not established facts.', ['Check index coverage and retrieval filters.', 'Fail explicitly or retry when required evidence is absent.']),
    'irrelevant_retrieval': ('Returned document IDs do not cover the required evidence. The retrieval query or corpus may be mismatched.', ['Inspect the query, corpus, and relevance labels.', 'Check retrieval filters and ranking before changing the answer prompt.']),
    'execution_deadline': ('The overall run deadline expired during execution or retry backoff.', ['Inspect the critical path and retry schedule.', 'Set a total retry budget within the execution deadline.']),
    'input_validation': ('The supplied input does not satisfy the adapter contract.', ['Compare input fields and types with the adapter schema.']),
}


def diagnose(run, spans, evaluation=None, evaluation_note=None):
    evaluation = evaluation or {'results': []}
    roots = [s for s in spans if s.parent_span_id is None]
    metadata = roots[0].span_metadata if roots else {}
    case = metadata.get('test_case_snapshot', {})
    expected_docs = case.get('expected_documents', [])
    origins, deadlines = error_origins(spans)
    findings = []
    for origin in origins:
        category, subtype, title = classify(origin, expected_docs, origin in deadlines)
        attempt = origin.span_metadata.get('attempt')
        recovered = [s for s in spans if s.name == origin.name and s.parent_span_id == origin.parent_span_id
                     and s.input == origin.input and s.error is None and s.ended_at is not None
                     and isinstance(attempt, int) and isinstance(s.span_metadata.get('attempt'), int)
                     and s.span_metadata['attempt'] > attempt and s.started_at >= (origin.ended_at or origin.started_at)]
        group = next((f for f in findings if f['subtype'] == subtype and f['component'] == origin.name and f['scope_parent_span_id'] == str(origin.parent_span_id)), None)
        if group:
            group['evidence_span_ids'].append(str(origin.id))
            group['observations'].append({'span_id': str(origin.id), 'error': origin.error,
                                          'attempt': origin.span_metadata.get('attempt'), 'output': origin.output})
            group['recovery_span_ids'] = list(dict.fromkeys(group['recovery_span_ids'] + [str(s.id) for s in recovered]))
            if not recovered:
                group['status'], group['severity'] = 'unresolved', 'high'
            continue
        explanation, actions = GUIDANCE.get(subtype, ('The error is observed, but its underlying cause cannot be established from this trace.', ['Inspect the failing span and its upstream dependencies.']))
        findings.append({'category': category, 'subtype': subtype, 'component': origin.name,
                         'scope_parent_span_id': str(origin.parent_span_id),
                         'title': title, 'severity': 'low' if recovered else 'high',
                         'status': 'recovered' if recovered else 'unresolved', 'role': 'observed_failure',
                         'evidence_level': 'observed', 'explanation': explanation,
                         'cause_status': 'unknown' if subtype not in ('execution_deadline','input_validation') else 'observed_condition',
                         'next_steps': actions, 'evidence_span_ids': [str(origin.id)],
                         'recovery_span_ids': [str(s.id) for s in recovered],
                         'evaluation_ids': [],
                         'observations': [{'span_id': str(origin.id), 'error': origin.error,
                                           'attempt': attempt, 'output': origin.output}]})
    # Evaluation verdicts describe failed checks, not necessarily the physical cause.
    specs = {'task_success': ('wrong_answer','reference_mismatch','Final response differs from the recorded reference'),
             'citation_validity': ('wrong_answer','citation_mismatch','Final citations are absent or not supported by retrieved IDs'),
             'groundedness': ('wrong_answer','groundedness_mismatch','Answer failed the scoped groundedness verifier'),
             'retrieval_recall': ('retrieval_failure','relevant_documents_missing','Required documents are missing from successful retrievals'),
             'latency': ('latency_breach','latency_budget','Run exceeded the configured latency budget')}
    for result in evaluation['results']:
        if result['passed'] is not False:
            continue
        name, detail = result['evaluator'], result['details']
        if name == 'task_success' and run.status != 'completed':
            continue  # Missing final output is a consequence of the failed execution.
        if name == 'retrieval_recall' and any(f['category'] == 'retrieval_failure' for f in findings):
            continue
        if name == 'tool_correctness':
            forbidden = detail.get('forbidden_calls', [])
            category, subtype, title = ('wrong_tool','forbidden_tool','A forbidden tool was called') if forbidden else ('missing_tool','required_tool_missing','A required tool was not called')
        elif name in specs:
            category, subtype, title = specs[name]
        else:
            continue
        component = 'final_response' if category == 'wrong_answer' else ('tool_selection' if name == 'tool_correctness' else name)
        findings.append({'category': category, 'subtype': subtype, 'component': component,
                         'title': title, 'severity': 'medium', 'status': 'unresolved',
                         'role': 'downstream_check' if run.status == 'failed' else 'evaluation_failure',
                         'evidence_level': 'observed_check', 'cause_status': 'unknown',
                         'explanation': detail['reason'] + ' This identifies a failed check; the reference or evaluator may also need review.',
                         'next_steps': ['Inspect the linked evaluation evidence and recorded expectations.', 'Validate the reference labels before changing agent behavior.'],
                         'evidence_span_ids': detail.get('evidence_span_ids', []), 'recovery_span_ids': [],
                         'evaluation_ids': [result['id']], 'observations': [detail]})
    if run.status == 'failed' and not any(f['role'] == 'observed_failure' for f in findings):
        findings.insert(0, {'category':'unknown', 'subtype':'insufficient_evidence', 'component':'agent',
                           'title':'Run failed without a localized trace error', 'severity':'high',
                           'status':'unresolved', 'role':'observed_failure', 'evidence_level':'unknown',
                           'cause_status':'unknown', 'explanation':'The run status reports failure, but available spans cannot localize its cause.',
                           'next_steps':['Instrument the failing boundary and capture its exception.'],
                           'evidence_span_ids':[], 'recovery_span_ids':[], 'evaluation_ids':[],
                           'observations':[{'run_error':run.error}]})
    # Associate an injection only when its event is a child of the failing span.
    # This is provenance, never an input to symptom classification.
    for finding in findings:
        ids = set(finding['evidence_span_ids'])
        injections = [s for s in spans if s.name == 'fault_decision' and str(s.parent_span_id) in ids
                      and isinstance(s.output, dict) and s.output.get('injected') is True]
        finding['injection_evidence'] = [{'span_id':str(s.id), 'kind':s.output.get('kind')} for s in injections]
        finding['fingerprint'] = fingerprint(finding['category'], finding['subtype'], finding['component'])
        finding['diagnosis_version'] = VERSION
    # Prefer unresolved direct failures, then failed checks, then recovered incidents.
    ordered = sorted(enumerate(findings), key=lambda pair: (pair[1]['status'] == 'recovered', pair[1]['role'] == 'downstream_check', pair[0]))
    primary = ordered[0][0] if ordered else None
    task = next((r['passed'] for r in evaluation['results'] if r['evaluator'] == 'task_success'), None)
    if run.status == 'failed':
        outcome = 'unknown' if primary is not None and findings[primary]['evidence_level'] == 'unknown' else 'failed'
    elif any(f['status'] == 'unresolved' for f in findings):
        outcome = 'checks_failed'
    elif findings:
        outcome = 'recovered'
    else:
        outcome = 'no_failure_observed'
    return {'run_id':str(run.id), 'diagnosis_version':VERSION, 'outcome':outcome,
            'task_passed':task, 'primary_index':primary, 'findings':findings,
            'evaluation_note':evaluation_note,
            'limitations':['Rules identify observed symptoms and failed checks, not unobserved service internals.',
                           'Recovery means a later matching step succeeded; run and task outcomes are reported separately.',
                           'No failure observed does not prove correctness, especially when evaluations are unavailable.',
                           'Similarity groups share a symptom signature, not a proven root cause.']}
