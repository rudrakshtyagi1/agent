"""Persist versioned evaluations independently from agent execution."""
import hashlib
import json
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.run import RunModel
from app.db.models.evaluation import EvaluationModel
from app.db.repositories.evaluation_repo import EvaluationRepository
from app.db.repositories.trace_repo import TraceSpanRepository
from app.evaluation.engine import VERSION, evaluate, aggregate
from app.schemas.evaluation import EvaluationResponse


def report(rows):
    results = [EvaluationResponse.model_validate(row).model_dump(mode='json') for row in rows]
    return {'evaluator_version': VERSION, 'results': results, 'summary': aggregate(results)}


async def evaluate_run(db: AsyncSession, run_id: UUID):
    run = await db.get(RunModel, run_id)
    if run is None:
        raise HTTPException(404, 'Run not found')
    if run.status not in ('completed', 'failed'):
        raise HTTPException(409, 'Only finished runs can be evaluated')
    # Serialize evaluate requests on the run row, including SQLite writers.
    await db.execute(update(RunModel).where(RunModel.id == run_id).values(status=RunModel.status))
    existing = await EvaluationRepository(db).list_by_run(run_id)
    existing = [r for r in existing if r.details.get('evaluator_version') == VERSION]
    if existing:
        return report(existing)
    spans = await TraceSpanRepository(db).list_by_run(run_id)
    roots = [s for s in spans if s.parent_span_id is None]
    snapshot = roots[0].span_metadata.get('test_case_snapshot') if roots else None
    if not isinstance(snapshot, dict):
        raise HTTPException(409, 'This trace predates evaluation snapshots. Create and execute a new run.')
    try:
        results = evaluate(run, spans, snapshot)
    except (ValidationError, TypeError, ValueError) as exc:
        raise HTTPException(422, 'Invalid recorded evaluation contract') from exc
    fingerprint = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    rows = []
    for result in results:
        result['details'].update({'expectations_sha256': fingerprint, 'trace_id': str(roots[0].trace_id)})
        row = EvaluationModel(run_id=run_id, **result)
        db.add(row)
        rows.append(row)
    await db.flush()
    return report(rows)
