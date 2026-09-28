"""Paired baseline/unprotected/retry runs against an identical frozen case."""
import hashlib
from uuid import uuid4
from app.chaos.engine import ENGINE_VERSION
from app.db.models.agent import AgentModel
from app.db.models.test_case import TestCaseModel
from app.db.models.run import RunModel
from app.db.models.chaos_campaign import ChaosCampaignModel
from app.db.repositories.trace_repo import TraceSpanRepository
from app.evaluation.service import evaluate_run
from app.runtime.executor import execute_run
from app.schemas.chaos import CampaignRequest, ExecutionOptions, FaultConfig
from app.target_agents.support import RUNTIME_VERSION


async def execute_case(db, agent, case, options):
    run = RunModel(id=uuid4(), agent_id=agent.id, agent_version=agent.version,
                   test_case_id=case.id, status='queued')
    db.add(run)
    await db.flush()
    await execute_run(db, run, options)
    evaluation = await evaluate_run(db, run.id)
    spans = await TraceSpanRepository(db).list_by_run(run.id)
    events = [s for s in spans if s.name == 'fault_decision']
    injected = [s for s in events if (s.output or {}).get('injected')]
    retries = [s for s in spans if s.name == 'retry_scheduled']
    task = next(r for r in evaluation['results'] if r['evaluator'] == 'task_success')
    return {'run_id': str(run.id), 'trace_id': str(spans[0].trace_id),
            'status': run.status, 'error': run.error, 'latency_ms': run.total_latency_ms,
            'task_passed': task['passed'], 'injected_count': len(injected),
            'retry_count': sum(s.name in ('retrieve_refund_policy', 'lookup_order') and s.span_metadata.get('attempt', 1) > 1 for s in spans),
            'scheduled_retry_count': len(retries),
            'attempts': {name: sum(s.name == name for s in spans)
                         for name in ('retrieve_refund_policy', 'lookup_order')},
            'fault_events': [{'span_id': str(s.id), **s.output} for s in events],
            'options': options.model_dump(), 'evaluation': evaluation}


async def run_campaign(db, request: CampaignRequest):
    campaign_id = uuid4()
    agent = AgentModel(id=uuid4(), name=f'Chaos support {campaign_id}', version='1.0.0',
                       endpoint='builtin://support', model='deterministic-template', status='active')
    case = TestCaseModel(id=uuid4(), name='Paired refund resilience', category='chaos',
                        input={'order_id': request.order_id, 'scenario': 'success'},
                        expected_tools=['lookup_order'], forbidden_tools=['issue_refund'],
                        expected_documents=['refund-policy-v1'],
                        tc_metadata={'evaluation': {'expected_output': {
                            'eligible': request.order_id == 'ORD-1001', 'citations': ['refund-policy-v1']},
                            'max_latency_ms': 1000}})
    db.add_all([agent, case])
    await db.flush()
    baseline = await execute_case(db, agent, case, ExecutionOptions())
    comparisons = []
    for kind in request.faults:
        fault = FaultConfig(kind=kind, seed=request.seed, probability=request.probability,
                            fail_first_attempts=request.fail_first_attempts)
        unprotected = await execute_case(db, agent, case, ExecutionOptions(fault=fault))
        protected = await execute_case(db, agent, case, ExecutionOptions(fault=fault, retry=request.retry))
        injected = protected['injected_count'] > 0
        # A completed run with no fired fault is not evidence of recovery.
        recovered = protected['task_passed'] is True if injected else None
        comparisons.append({'fault': kind, 'unprotected': unprotected, 'protected': protected,
                            'recovered': recovered,
                            'retry_rescued_task': unprotected['task_passed'] is False and protected['task_passed'] is True,
                            'latency_delta_ms': protected['latency_ms'] - baseline['latency_ms']})
    observed = [c for c in comparisons if c['recovered'] is not None]
    result = {'id': str(campaign_id), 'engine_version': ENGINE_VERSION,
              'runtime_version': RUNTIME_VERSION, 'config': request.model_dump(),
              'config_sha256': hashlib.sha256(request.model_dump_json().encode()).hexdigest(),
              'baseline': baseline, 'comparisons': comparisons,
              'summary': {'fault_types': len(comparisons), 'injected_cases': len(observed),
                          'not_injected_cases': len(comparisons) - len(observed),
                          'recovered_cases': sum(c['recovered'] is True for c in observed),
                          'recovery_rate': sum(c['recovered'] is True for c in observed)/len(observed) if observed else None,
                          'retry_rescued_cases': sum(c['retry_rescued_task'] for c in comparisons)},
              'limitations': 'Local fixture faults only. Seed reproduces injection decisions, not timing. Recovery measures labeled task success after a fired fault; no statistical production reliability claim.'}
    db.add(ChaosCampaignModel(id=campaign_id, report=result))
    await db.flush()
    return result
