"""Local fault catalog, bounded campaign execution, and persisted reports."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db.models.chaos_campaign import ChaosCampaignModel
from app.chaos.campaigns import run_campaign
from app.chaos.engine import ENGINE_VERSION, TARGETS
from app.schemas.chaos import CampaignRequest

router = APIRouter(prefix='/chaos', tags=['Chaos testing'])


@router.get('/faults')
async def fault_catalog():
    return {'engine_version': ENGINE_VERSION, 'faults': [
        {'kind': kind, 'target': target} for kind, target in TARGETS.items()]}


@router.post('/campaigns', status_code=201)
async def create_campaign(payload: CampaignRequest, db: AsyncSession = Depends(get_db)):
    report = await run_campaign(db, payload)
    await db.commit()
    return report


@router.get('/campaigns')
async def list_campaigns(limit: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ChaosCampaignModel).order_by(ChaosCampaignModel.created_at.desc()).limit(limit))).scalars()
    return [{'id': str(r.id), 'created_at': r.created_at, 'summary': r.report['summary']} for r in rows]


@router.get('/campaigns/{campaign_id}')
async def get_campaign(campaign_id: UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(ChaosCampaignModel, campaign_id)
    if row is None:
        raise HTTPException(404, 'Chaos campaign not found')
    return row.report
