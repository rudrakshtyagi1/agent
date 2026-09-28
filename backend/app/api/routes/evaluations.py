"""Evaluate stored runs and execute the bundled diagnostic suite."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db.models.run import RunModel
from app.db.models.evaluation_suite import EvaluationSuiteModel
from app.db.repositories.evaluation_repo import EvaluationRepository
from app.evaluation.engine import VERSION
from app.evaluation.service import evaluate_run, report
from app.evaluation.suites import dataset, run_suite

router = APIRouter(tags=['Evaluations'])


@router.post('/runs/{run_id}/evaluate')
async def evaluate_endpoint(run_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await evaluate_run(db, run_id)
    await db.commit()
    return result


@router.get('/runs/{run_id}/evaluations')
async def get_evaluations(run_id: UUID, db: AsyncSession = Depends(get_db)):
    if await db.get(RunModel, run_id) is None:
        raise HTTPException(404, 'Run not found')
    rows = await EvaluationRepository(db).list_by_run(run_id)
    return report([r for r in rows if r.details.get('evaluator_version') == VERSION])


@router.get('/evaluation-datasets')
async def list_datasets():
    data = dataset()
    return [{'id': 'support-agent', 'name': data['name'], 'version': data['version'],
             'description': data['description'], 'case_count': len(data['cases'])}]


@router.post('/evaluation-suites/support-agent', status_code=201)
async def execute_suite(db: AsyncSession = Depends(get_db)):
    result = await run_suite(db)
    await db.commit()
    return result


@router.get('/evaluation-suites')
async def list_suites(limit: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(EvaluationSuiteModel).order_by(EvaluationSuiteModel.created_at.desc()).limit(limit))).scalars()
    return [{'id': str(row.id), 'dataset_version': row.dataset_version,
             'created_at': row.created_at, 'summary': row.report['summary']} for row in rows]


@router.get('/evaluation-suites/{suite_id}')
async def get_suite(suite_id: UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(EvaluationSuiteModel, suite_id)
    if row is None:
        raise HTTPException(404, 'Evaluation suite not found')
    return row.report
