"""Integration tests — Agent, TestCase, and Run API endpoints."""

import uuid
import pytest
from httpx import AsyncClient


# ------------------------------------------------------------------ #
# Agent Endpoints
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_create_and_get_agent(client: AsyncClient):
    """Register an agent, fetch it by ID, and list all agents."""
    payload = {
        "name": "support-agent",
        "version": "1.0.0",
        "description": "Customer support bot",
        "endpoint": "http://localhost:8001/chat",
        "model": "llama3.2",
        "status": "active",
        "metadata": {"team": "customer_success", "env": "staging"},
    }
    # 1. Create agent
    resp = await client.post("/api/v1/agents", json=payload)
    assert resp.status_code == 201
    created = resp.json()
    assert created["name"] == "support-agent"
    assert created["version"] == "1.0.0"
    assert created["status"] == "active"
    assert created["metadata"]["team"] == "customer_success"
    agent_id = created["id"]
    assert agent_id is not None

    # 2. Get by ID
    get_resp = await client.get(f"/api/v1/agents/{agent_id}")
    assert get_resp.status_code == 200
    fetched = get_resp.json()
    assert fetched["id"] == agent_id
    assert fetched["name"] == "support-agent"

    # 3. List agents
    list_resp = await client.get("/api/v1/agents")
    assert list_resp.status_code == 200
    agents = list_resp.json()
    assert len(agents) >= 1
    assert any(a["id"] == agent_id for a in agents)


@pytest.mark.asyncio
async def test_duplicate_agent_conflict(client: AsyncClient):
    """Creating the same agent name and version twice should return 409 Conflict."""
    payload = {
        "name": "duplicate-agent",
        "version": "0.1.0",
        "status": "active",
    }
    resp1 = await client.post("/api/v1/agents", json=payload)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/v1/agents", json=payload)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_get_nonexistent_agent(client: AsyncClient):
    """Requesting an unknown agent ID should return 404."""
    random_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/agents/{random_id}")
    assert resp.status_code == 404


# ------------------------------------------------------------------ #
# TestCase Endpoints
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_create_and_get_test_case(client: AsyncClient):
    """Create a TestCase, retrieve by ID, and list with category filtering."""
    payload = {
        "name": "Refund Order Verification",
        "description": "Verifies support agent processes legitimate refunds",
        "category": "golden",
        "input": {"order_id": "ORD-1234", "issue": "damaged_goods"},
        "expected_tools": ["get_order", "refund_order"],
        "forbidden_tools": ["cancel_order"],
        "expected_documents": ["refund_policy.md"],
        "expected_behavior": "Look up order and issue refund if within 30 days",
        "tags": ["refund", "e-commerce"],
        "metadata": {"priority": "p0"},
    }
    # 1. Create test case
    resp = await client.post("/api/v1/test-cases", json=payload)
    assert resp.status_code == 201
    created = resp.json()
    assert created["name"] == "Refund Order Verification"
    assert created["category"] == "golden"
    assert created["expected_tools"] == ["get_order", "refund_order"]
    tc_id = created["id"]
    assert tc_id is not None

    # 2. Get by ID
    get_resp = await client.get(f"/api/v1/test-cases/{tc_id}")
    assert get_resp.status_code == 200
    fetched = get_resp.json()
    assert fetched["id"] == tc_id
    assert fetched["category"] == "golden"

    # 3. List test cases with category filter
    list_resp = await client.get("/api/v1/test-cases?category=golden")
    assert list_resp.status_code == 200
    cases = list_resp.json()
    assert len(cases) >= 1
    assert all(c["category"] == "golden" for c in cases)


@pytest.mark.asyncio
async def test_get_nonexistent_test_case(client: AsyncClient):
    """Requesting an unknown test case ID should return 404."""
    random_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/test-cases/{random_id}")
    assert resp.status_code == 404


# ------------------------------------------------------------------ #
# Run Endpoints
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_create_and_get_run_lifecycle(client: AsyncClient):
    """
    End-to-end verification:
    Agent -> TestCase -> Run creation.
    Verifies that:
    1. Run is created in QUEUED status.
    2. Agent version is denormalised and preserved for historical replay.
    3. Run can be retrieved by ID and listed.
    """
    # 1. Create Agent
    agent_resp = await client.post(
        "/api/v1/agents",
        json={"name": "e2e-agent", "version": "1.2.3", "status": "active"},
    )
    assert agent_resp.status_code == 201
    agent = agent_resp.json()
    agent_id = agent["id"]

    # 2. Create TestCase
    tc_resp = await client.post(
        "/api/v1/test-cases",
        json={
            "name": "e2e-cancellation",
            "category": "functional",
            "input": {"action": "cancel", "order_id": "ORD-999"},
        },
    )
    assert tc_resp.status_code == 201
    tc = tc_resp.json()
    tc_id = tc["id"]

    # 3. Create Run (Agent + TestCase)
    run_payload = {
        "agent_id": agent_id,
        "agent_version": agent["version"],
        "test_case_id": tc_id,
    }
    run_resp = await client.post("/api/v1/runs", json=run_payload)
    assert run_resp.status_code == 201
    created_run = run_resp.json()
    run_id = created_run["id"]

    assert created_run["status"] == "queued"
    assert created_run["agent_id"] == agent_id
    assert created_run["agent_version"] == "1.2.3"
    assert created_run["test_case_id"] == tc_id
    assert created_run["started_at"] is None
    assert created_run["completed_at"] is None

    # 4. Get Run by ID
    get_run_resp = await client.get(f"/api/v1/runs/{run_id}")
    assert get_run_resp.status_code == 200
    fetched_run = get_run_resp.json()
    assert fetched_run["id"] == run_id
    assert fetched_run["agent_version"] == "1.2.3"

    # 5. List runs with filters
    list_runs_resp = await client.get(f"/api/v1/runs?agent_id={agent_id}&status=queued")
    assert list_runs_resp.status_code == 200
    runs = list_runs_resp.json()
    assert len(runs) >= 1
    assert any(r["id"] == run_id for r in runs)


@pytest.mark.asyncio
async def test_run_creation_fails_with_invalid_foreign_keys(client: AsyncClient):
    """Creating a run with a nonexistent agent or test case must fail with 404."""
    real_agent = (
        await client.post(
            "/api/v1/agents",
            json={"name": "fk-test-agent", "version": "1.0.0"},
        )
    ).json()
    real_tc = (
        await client.post(
            "/api/v1/test-cases",
            json={"name": "fk-test-tc", "category": "golden"},
        )
    ).json()

    fake_id = str(uuid.uuid4())

    # Invalid agent
    resp_invalid_agent = await client.post(
        "/api/v1/runs",
        json={
            "agent_id": fake_id,
            "agent_version": "1.0.0",
            "test_case_id": real_tc["id"],
        },
    )
    assert resp_invalid_agent.status_code == 404
    assert "Agent" in resp_invalid_agent.json()["error"]

    # Invalid test case
    resp_invalid_tc = await client.post(
        "/api/v1/runs",
        json={
            "agent_id": real_agent["id"],
            "agent_version": "1.0.0",
            "test_case_id": fake_id,
        },
    )
    assert resp_invalid_tc.status_code == 404
    assert "TestCase" in resp_invalid_tc.json()["error"]
