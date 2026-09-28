"""Evidence-based diagnosis and similar symptom groups."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db.models.run import RunModel
from app.db.models.diagnosis import DiagnosisModel, DiagnosisBenchmarkModel
from app.failure_intelligence.failure_memory import diagnose_run, grouped_failures
from app.failure_intelligence.root_cause import VERSION
from app.failure_intelligence.benchmark import run_benchmark

router = APIRouter(tags=['Failure intelligence'])


@router.post('/runs/{run_id}/diagnose')
async def analyze(run_id:UUID,db:AsyncSession=Depends(get_db)):
    result = await diagnose_run(db,run_id)
    await db.commit()
    return result


@router.get('/runs/{run_id}/diagnosis')
async def get_diagnosis(run_id:UUID,db:AsyncSession=Depends(get_db)):
    if await db.get(RunModel,run_id) is None:
        raise HTTPException(404,'Run not found')
    row = (await db.execute(select(DiagnosisModel).where(DiagnosisModel.run_id==run_id,DiagnosisModel.version==VERSION))).scalar_one_or_none()
    return row.report if row else None


@router.post('/failures/analyze-recent')
async def analyze_recent(limit:int=Query(20,ge=1,le=50),db:AsyncSession=Depends(get_db)):
    runs = (await db.execute(select(RunModel).where(RunModel.status.in_(['completed','failed'])).order_by(RunModel.created_at.desc()).limit(limit))).scalars().all()
    results = [await diagnose_run(db,run.id) for run in runs]
    await db.commit()
    return {'analyzed':len(results),'reports':results}


@router.get('/failures/groups')
async def groups(db:AsyncSession=Depends(get_db)):
    return await grouped_failures(db)


@router.post('/failures/benchmark',status_code=201)
async def benchmark(db:AsyncSession=Depends(get_db)):
    result = await run_benchmark(db)
    await db.commit()
    return result


@router.get('/failures/benchmarks/latest')
async def latest_benchmark(db:AsyncSession=Depends(get_db)):
    row = (await db.execute(select(DiagnosisBenchmarkModel).order_by(DiagnosisBenchmarkModel.created_at.desc()).limit(1))).scalar_one_or_none()
    return row.report if row else None
