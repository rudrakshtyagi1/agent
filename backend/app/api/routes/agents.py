"""Agent CRUD routes."""

from __future__ import annotations

import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.repositories.agent_repo import AgentRepository
from app.db.models.agent import AgentModel
from app.schemas.agent import AgentCreate, AgentResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents", tags=["Agents"])


def _model_to_response(agent: AgentModel) -> AgentResponse:
    """Convert ORM model to API response schema."""
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        version=agent.version,
        description=agent.description,
        endpoint=agent.endpoint,
        model=agent.model,
        status=agent.status,
        metadata=agent.agent_metadata or {},
        created_at=agent.created_at,
    )


@router.post(
    "",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new agent",
)
async def create_agent(
    payload: AgentCreate,
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    """Register a new agent version in the platform."""
    repo = AgentRepository(db)
    # Enforce uniqueness at application layer before DB constraint fires
    existing = await repo.get_by_name_and_version(payload.name, payload.version)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent '{payload.name}' version '{payload.version}' already exists.",
        )
    agent = await repo.create(
        id=uuid.uuid4(),
        name=payload.name,
        version=payload.version,
        description=payload.description,
        endpoint=payload.endpoint,
        model=payload.model,
        status=payload.status.value,
        agent_metadata=payload.metadata,
    )
    logger.info("Registered agent '%s' version '%s' id=%s", agent.name, agent.version, agent.id)
    return _model_to_response(agent)


@router.get(
    "",
    response_model=list[AgentResponse],
    summary="List all registered agents",
)
async def list_agents(
    offset: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> list[AgentResponse]:
    """Return a paginated list of all registered agents."""
    repo = AgentRepository(db)
    agents = await repo.list(offset=offset, limit=limit)
    return [_model_to_response(a) for a in agents]


@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Get agent by ID",
)
async def get_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    """Retrieve a single agent by its UUID."""
    repo = AgentRepository(db)
    agent = await repo.get_by_id(agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found.",
        )
    return _model_to_response(agent)
