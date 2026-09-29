from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_readiness_requires_database_and_recent_worker(test_engine, monkeypatch):
    from app.main import app
    from app.db import session
    from sqlalchemy.ext.asyncio import async_sessionmaker

    monkeypatch.setattr(session, "_session_factory", async_sessionmaker(test_engine))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for health in (
            {},
            {"last_success": datetime.now(timezone.utc).isoformat(), "error": "failed"},
            {
                "last_success": (
                    datetime.now(timezone.utc) - timedelta(minutes=5)
                ).isoformat()
            },
        ):
            app.state.monitor_health = health
            assert (await client.get("/ready")).status_code == 503
        app.state.monitor_health = {
            "last_success": datetime.now(timezone.utc).isoformat(),
            "error": None,
        }
        assert (await client.get("/ready")).status_code == 200
        monkeypatch.setattr(session, "_session_factory", None)
        response = await client.get("/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "not_ready"}
