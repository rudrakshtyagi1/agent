"""TestCase CRUD routes."""

from __future__ import annotations

import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.repositories.test_case_repo import TestCaseRepository
from app.db.models.test_case import TestCaseModel
from app.schemas.test_case import TestCaseCategory, TestCaseCreate, TestCaseResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/test-cases", tags=["Test Cases"])


def _model_to_response(tc: TestCaseModel) -> TestCaseResponse:
    return TestCaseResponse(
        id=tc.id,
        name=tc.name,
        description=tc.description,
        category=tc.category,
        input=tc.input or {},
        expected_tools=tc.expected_tools or [],
        forbidden_tools=tc.forbidden_tools or [],
        expected_documents=tc.expected_documents or [],
        expected_behavior=tc.expected_behavior,
        tags=tc.tags or [],
        metadata=tc.tc_metadata or {},
        created_at=tc.created_at,
    )


@router.post(
    "",
    response_model=TestCaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new test case",
)
async def create_test_case(
    payload: TestCaseCreate,
    db: AsyncSession = Depends(get_db),
) -> TestCaseResponse:
    """Persist a new test case definition."""
    repo = TestCaseRepository(db)
    tc = await repo.create(
        id=uuid.uuid4(),
        name=payload.name,
        description=payload.description,
        category=payload.category.value,
        input=payload.input,
        expected_tools=payload.expected_tools,
        forbidden_tools=payload.forbidden_tools,
        expected_documents=payload.expected_documents,
        expected_behavior=payload.expected_behavior,
        tags=payload.tags,
        tc_metadata=payload.metadata,
    )
    logger.info("Created test case '%s' id=%s", tc.name, tc.id)
    return _model_to_response(tc)


@router.get(
    "",
    response_model=list[TestCaseResponse],
    summary="List test cases",
)
async def list_test_cases(
    offset: int = 0,
    limit: int = 100,
    category: TestCaseCategory | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[TestCaseResponse]:
    """Return a paginated list of test cases, optionally filtered by category."""
    repo = TestCaseRepository(db)
    if category is not None:
        cases = await repo.list_by_category(category.value)
        # Apply offset/limit manually when using domain method
        cases = cases[offset : offset + limit]
    else:
        cases = await repo.list(offset=offset, limit=limit)
    return [_model_to_response(tc) for tc in cases]


@router.get(
    "/{test_case_id}",
    response_model=TestCaseResponse,
    summary="Get test case by ID",
)
async def get_test_case(
    test_case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> TestCaseResponse:
    """Retrieve a single test case by its UUID."""
    repo = TestCaseRepository(db)
    tc = await repo.get_by_id(test_case_id)
    if tc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TestCase '{test_case_id}' not found.",
        )
    return _model_to_response(tc)
