"""Diagnostic fixture audit. Hide injector events/config from blind predictions."""
from types import SimpleNamespace
from uuid import UUID, uuid4
from app.chaos.campaigns import run_campaign
from app.schemas.chaos import CampaignRequest
from app.db.models.run import RunModel
from app.db.models.diagnosis import DiagnosisBenchmarkModel
from app.db.repositories.trace_repo import TraceSpanRepository
from app.failure_intelligence.root_cause import VERSION, diagnose
from app.failure_intelligence.failure_memory import diagnose_run


async def run_benchmark(db):
    campaign = await run_campaign(db, CampaignRequest())
    samples = []
    cases = [(campaign['baseline'],None,'no_failure_observed')]
    for pair in campaign['comparisons']:
        cases.extend([(pair['unprotected'],pair['fault'],'failed'),
                      (pair['protected'],pair['fault'],'recovered')])
    for source, expected, outcome in cases:
        run = await db.get(RunModel,UUID(source['run_id']))
        spans = await TraceSpanRepository(db).list_by_run(run.id)
        blind = []
        for span in spans:
            if span.name == 'fault_decision':
                continue
            fields = {key:getattr(span,key) for key in ('id','parent_span_id','span_type','name','input','output','error','started_at','ended_at')}
            fields['span_metadata'] = {k:v for k,v in span.span_metadata.items() if k not in ('execution_options','chaos_engine_version')}
            blind.append(SimpleNamespace(**fields))
        result = diagnose(run,blind,source['evaluation'])
        predicted = result['findings'][result['primary_index']]['subtype'] if result['primary_index'] is not None else None
        samples.append({'run_id':str(run.id),'expected_subtype':expected,'predicted_subtype':predicted,
                        'expected_outcome':outcome,'predicted_outcome':result['outcome'],
                        'correct':predicted==expected and result['outcome']==outcome})
        await diagnose_run(db,run.id)
    report = {'id':str(uuid4()),'diagnosis_version':VERSION,'fixture_version':'chaos-four-faults/1.0.0',
              'campaign_id':campaign['id'],'samples':samples,'correct':sum(s['correct'] for s in samples),
              'total':len(samples),'accuracy':sum(s['correct'] for s in samples)/len(samples),
              'blind_inputs':'Injection-decision spans and root execution/fault configuration removed before classification.',
              'limitations':'Nine deterministic fixtures (four failures, four recoveries, one clean run). This is a regression audit, not held-out real-world accuracy.'}
    db.add(DiagnosisBenchmarkModel(id=UUID(report['id']),report=report))
    await db.flush()
    return report
