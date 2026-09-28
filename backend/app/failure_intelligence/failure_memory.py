"""Persist diagnoses and symptom records without modifying execution outcomes."""
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select, update
from app.db.models.run import RunModel
from app.db.models.failure import FailureModel
from app.db.models.diagnosis import DiagnosisModel
from app.db.repositories.trace_repo import TraceSpanRepository
from app.evaluation.service import evaluate_run
from app.failure_intelligence.root_cause import VERSION, diagnose


async def diagnose_run(db, run_id):
    run = await db.get(RunModel,run_id)
    if run is None:
        raise HTTPException(404,'Run not found')
    if run.status not in ('completed','failed'):
        raise HTTPException(409,'Only finished runs can be diagnosed')
    await db.execute(update(RunModel).where(RunModel.id==run_id).values(status=RunModel.status))
    saved = (await db.execute(select(DiagnosisModel).where(DiagnosisModel.run_id==run_id,DiagnosisModel.version==VERSION))).scalar_one_or_none()
    if saved:
        return saved.report
    spans = await TraceSpanRepository(db).list_by_run(run_id)
    evaluation, note = None, None
    try:
        evaluation = await evaluate_run(db,run_id)
    except HTTPException as exc:
        if exc.status_code not in (409,422):
            raise
        note = str(exc.detail)
    result = diagnose(run,spans,evaluation,note)
    for finding in result['findings']:
        failure_id = uuid4()
        finding['id'] = str(failure_id)
        db.add(FailureModel(id=failure_id,run_id=run_id,category=finding['category'],severity=finding['severity'],
                            title=finding['title'],description=finding['explanation'],
                            suspected_component=finding['component'],evidence=finding))
    result['primary_finding_id'] = result['findings'][result['primary_index']]['id'] if result['primary_index'] is not None else None
    db.add(DiagnosisModel(run_id=run_id,version=VERSION,report=result))
    await db.flush()
    return result


async def grouped_failures(db):
    # Bounded window for this local app; report the scope rather than implying all-time totals.
    rows = (await db.execute(select(FailureModel).order_by(FailureModel.created_at.desc(),FailureModel.id).limit(500))).scalars().all()
    groups = {}
    for row in rows:
        evidence = row.evidence
        if evidence.get('diagnosis_version') != VERSION:
            continue
        key = evidence['fingerprint']
        group = groups.setdefault(key,{'fingerprint':key,'category':row.category,'subtype':evidence['subtype'],
                                      'component':row.suspected_component,'title':row.title,
                                      'occurrences':0,'recovered':0,'runs':[]})
        group['occurrences'] += 1
        group['recovered'] += evidence['status'] == 'recovered'
        group['runs'].append({'run_id':str(row.run_id),'failure_id':str(row.id),'status':evidence['status']})
    return {'diagnosis_version':VERSION,'window':'Most recent 500 failure records',
            'records_scanned':len(rows),'groups':sorted(groups.values(),key=lambda g:-g['occurrences'])}
