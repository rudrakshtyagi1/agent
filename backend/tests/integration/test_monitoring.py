import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.config import get_settings
from app.db.models.monitoring import MonitorTrace, MonitorAlert
from app.monitoring.service import process_batch


def payload(failed=False):
    root = str(uuid4())
    child = str(uuid4())
    start = datetime.now(timezone.utc)
    span = {
        "id": root,
        "name": "root",
        "span_type": "planner",
        "started_at": start.isoformat(),
        "ended_at": (start + timedelta(milliseconds=20)).isoformat(),
    }
    return {
        "trace_id": str(uuid4()),
        "agent_name": "external",
        "agent_version": "v1",
        "status": "failed" if failed else "completed",
        "spans": [
            span,
            {
                **span,
                "id": child,
                "parent_span_id": root,
                "name": "tool",
                "span_type": "tool_call",
                "error": "secret=hidden a@b.com" if failed else None,
                "input": {"password": "hidden"},
                "output": {"text": "a@b.com"},
            },
        ],
    }


@pytest.mark.asyncio
async def test_tenant_auth_redaction_idempotency_and_processing(
    client, test_engine, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "monitor_keys", {"alpha": "a" * 32, "beta": "b" * 32})
    data = payload(True)
    headers = {"Authorization": "Bearer " + "a" * 32}
    assert (
        await client.post("/api/v1/monitoring/traces", json=data)
    ).status_code == 401
    response = await client.post(
        "/api/v1/monitoring/traces", json=data, headers=headers
    )
    assert response.status_code == 202, response.text
    row = response.json()
    duplicate = (
        await client.post("/api/v1/monitoring/traces", json=data, headers=headers)
    ).json()
    assert duplicate["duplicate"] and duplicate["id"] == row["id"]
    data["agent_version"] = "different"
    assert (
        await client.post("/api/v1/monitoring/traces", json=data, headers=headers)
    ).status_code == 409
    url = "/api/v1/monitoring/traces/" + row["id"]
    assert (
        await client.get(url, headers={"Authorization": "Bearer " + "b" * 32})
    ).status_code == 404
    assert (
        await client.get(
            "/api/v1/monitoring/traces", headers={"Authorization": "Bearer " + "b" * 32}
        )
    ).json() == []
    await process_batch(
        async_sessionmaker(test_engine, expire_on_commit=False), settings
    )
    result = (await client.get(url, headers=headers)).json()
    assert result["status"] == "processed"
    assert result["summary"]["observed_failure"]["name"] == "tool"
    assert result["summary"]["task_success"] is None
    assert "hidden" not in str(result) and "a@b.com" not in str(result)
    assert result["payload"]["spans"][1]["input"] is None
    assert (await client.get("/api/v1/monitoring/overview", headers=headers)).json()[
        "admission"
    ]["accepted"] == 1


@pytest.mark.asyncio
async def test_limits_validation_sampling_and_queue_retry(
    client, test_engine, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "monitor_queue_capacity", 1)
    first = payload()
    assert (
        await client.post("/api/v1/monitoring/traces", json=first)
    ).status_code == 202
    second = payload()
    assert (
        await client.post("/api/v1/monitoring/traces", json=second)
    ).status_code == 429
    await process_batch(
        async_sessionmaker(test_engine, expire_on_commit=False), settings
    )
    assert (
        await client.post("/api/v1/monitoring/traces", json=second)
    ).status_code == 202
    bad = payload()
    bad["spans"][1]["parent_span_id"] = str(uuid4())
    assert (await client.post("/api/v1/monitoring/traces", json=bad)).status_code == 422
    bad = payload()
    bad["spans"][0]["started_at"] = "private-secret"
    response = await client.post("/api/v1/monitoring/traces", json=bad)
    assert response.status_code == 422 and "private-secret" not in response.text
    assert (
        await client.post("/api/v1/monitoring/traces", content=b"x" * 524289)
    ).status_code == 413
    monkeypatch.setattr(settings, "monitor_sample_rate", 0)
    assert (await client.post("/api/v1/monitoring/traces", json=payload())).json()[
        "status"
    ] == "sampled_out"
    overview = (await client.get("/api/v1/monitoring/overview")).json()
    assert (
        overview["admission"]["rejected"] == 1
        and overview["admission"]["sampled_out"] == 1
    )
    assert overview["admission"]["dropped_spans"] == 4


@pytest.mark.asyncio
async def test_alert_transitions_and_retention(client, test_engine, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "monitor_window", 5)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    for i in range(5):
        await client.post("/api/v1/monitoring/traces", json=payload(i == 0))
    await process_batch(factory, settings)
    alerts = (await client.get("/api/v1/monitoring/alerts")).json()
    assert len(alerts) == 1 and alerts[0]["status"] == "open"
    await process_batch(factory, settings)
    assert len((await client.get("/api/v1/monitoring/alerts")).json()) == 1
    await client.post("/api/v1/monitoring/traces", json=payload())
    await process_batch(factory, settings)
    assert (await client.get("/api/v1/monitoring/alerts")).json()[0][
        "status"
    ] == "resolved"
    async with factory() as db:
        rows = (await db.execute(select(MonitorTrace))).scalars().all()
        for row in rows:
            row.created_at = datetime.now(timezone.utc) - timedelta(days=8)
        await db.commit()
    await process_batch(factory, settings)
    assert (await client.get("/api/v1/monitoring/traces")).json() == []


@pytest.mark.asyncio
async def test_hardened_mode_disables_legacy_and_requires_auth(
    test_engine, monkeypatch
):
    from app.main import create_app
    from httpx import AsyncClient, ASGITransport

    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(ValueError):
        create_app()
    monkeypatch.setattr(settings, "monitor_keys", {"a": "x" * 32})
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/api/v1/runs")).status_code == 404
        assert (await client.get("/docs")).status_code == 404
        assert (await client.get("/api/v1/monitoring/traces")).status_code == 401


@pytest.mark.asyncio
async def test_queue_survives_engine_recreation(tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.db.session import Base
    from app.monitoring.schemas import IncomingTrace
    from app.monitoring.service import admit
    from app.config import Settings

    url = f"sqlite+aiosqlite:///{tmp_path}/monitor.db"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(_env_file=None)
    async with factory() as db:
        saved = await admit(
            db, "tenant", IncomingTrace.model_validate(payload()), settings
        )
    await engine.dispose()
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    await process_batch(factory, settings)
    async with factory() as db:
        row = await db.get(MonitorTrace, saved["id"])
        assert row.status == "processed" and row.summary["span_count"] == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_opt_in_redaction_and_token_metrics(client, test_engine, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "monitor_capture_payloads", True)
    data = payload(True)
    span = data["spans"][1]
    span.update(
        span_type="model",
        input_tokens=12,
        output_tokens=4,
        metadata={
            "nested": {"Authorization": "Bearer abc123", "safe": "email a@b.com"}
        },
        output={"answer": "token=abc phone +1 202 555 0199"},
    )
    row = (await client.post("/api/v1/monitoring/traces", json=data)).json()
    await process_batch(
        async_sessionmaker(test_engine, expire_on_commit=False), settings
    )
    response = (await client.get("/api/v1/monitoring/traces/" + row["id"])).json()
    text = str(response)
    assert (
        "abc123" not in text
        and "a@b.com" not in text
        and "hidden" not in text
        and "555 0199" not in text
    )
    assert response["summary"]["reported_tokens"] == 16


@pytest.mark.asyncio
async def test_concurrent_admission_never_exceeds_capacity(tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.db.session import Base
    from app.monitoring.schemas import IncomingTrace
    from app.monitoring.service import admit
    from app.config import Settings
    from fastapi import HTTPException

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/concurrent.db")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(_env_file=None, monitor_queue_capacity=1)

    async def submit():
        async with factory() as db:
            try:
                return await admit(
                    db, "a", IncomingTrace.model_validate(payload()), settings
                )
            except HTTPException as error:
                return error.status_code

    results = await asyncio.gather(submit(), submit(), submit())
    assert results.count(429) == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_monitoring_errors_never_rethrow_payload_to_server_logger(
    client, monkeypatch, caplog
):
    from app.api.routes import monitoring

    async def broken(*args):
        raise RuntimeError("secret-telemetry-in-db-exception")

    monkeypatch.setattr(monitoring, "admit", broken)
    response = await client.post("/api/v1/monitoring/traces", json=payload())
    assert response.status_code == 500
    assert (
        "secret-telemetry" not in response.text
        and "secret-telemetry" not in caplog.text
    )
