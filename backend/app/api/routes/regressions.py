"""Paired comparisons, persisted gate reports, and strict boundary playback."""
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db.models.regression import RegressionReportModel
from app.schemas.regression import ComparisonRequest,ReplayRequest
from app.reliability.version_compare import run_comparison
from app.replay.comparator import replay_run
from app.target_agents.support import VERSIONS,PROVENANCE

router=APIRouter(tags=['Regression and release gates'])


@router.get('/regressions/versions')
async def versions():
    return {'versions':VERSIONS,'provenance':PROVENANCE}


@router.post('/regressions/compare',status_code=201)
async def compare(payload:ComparisonRequest,db:AsyncSession=Depends(get_db)):
    report=await run_comparison(db,payload)
    await db.commit()
    return report


@router.get('/regressions/reports')
async def history(limit:int=Query(20,ge=1,le=100),db:AsyncSession=Depends(get_db)):
    rows=(await db.execute(select(RegressionReportModel).order_by(RegressionReportModel.created_at.desc()).limit(limit))).scalars()
    return [{'id':str(r.id),'created_at':r.created_at,'request':r.report['request'],'gate_status':r.report['gate']['status']} for r in rows]


@router.get('/regressions/reports/{report_id}')
async def get_report(report_id:UUID,db:AsyncSession=Depends(get_db)):
    row=await db.get(RegressionReportModel,report_id)
    if row is None:
        raise HTTPException(404,'Comparison report not found')
    return row.report


@router.post('/runs/{source_id}/replay',status_code=201)
async def replay(source_id:UUID,payload:ReplayRequest,db:AsyncSession=Depends(get_db)):
    result=await replay_run(db,source_id,payload.candidate_version)
    await db.commit()
    return result
