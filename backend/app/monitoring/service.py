"""Durable single-process queue, observable admission, and windowed alerts."""

import asyncio
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import select, func, delete
from fastapi import HTTPException
from app.db.models.monitoring import MonitorTrace, MonitorTenant, MonitorAlert, now
from app.monitoring.security import minimize

# Serializes admission and processing within the supported one-process deployment.
# Do not run multiple uvicorn workers until DB-level queue claims are implemented.
queue_lock = asyncio.Lock()


def scope_of(payload):
    return json.dumps(
        [payload["agent_name"], payload["agent_version"], payload["environment"]]
    )


def summarize(payload):
    spans = payload["spans"]
    root = next(s for s in spans if s["parent_span_id"] is None)
    latency = (
        datetime.fromisoformat(root["ended_at"])
        - datetime.fromisoformat(root["started_at"])
    ).total_seconds() * 1000
    errors = [s for s in spans if s["error"]]
    leaves = [
        s
        for s in errors
        if not any(c["parent_span_id"] == s["id"] and c["error"] for c in errors)
    ]
    observed = (
        min(leaves, key=lambda s: datetime.fromisoformat(s["started_at"]))
        if leaves
        else None
    )
    models = [s for s in spans if s["span_type"] == "model"]
    tokens = (
        sum(s["input_tokens"] + s["output_tokens"] for s in models)
        if models
        and all(
            s["input_tokens"] is not None and s["output_tokens"] is not None
            for s in models
        )
        else None
    )
    return {
        "agent_name": payload["agent_name"],
        "agent_version": payload["agent_version"],
        "environment": payload["environment"],
        "scope": scope_of(payload),
        "execution_status": payload["status"],
        "latency_ms": round(latency, 3),
        "span_count": len(spans),
        "error_spans": len(errors),
        "reported_tokens": tokens,
        "observed_failure": (
            {"span_id": observed["id"], "name": observed["name"]} if observed else None
        ),
        "task_success": None,
        "note": "Execution health only; external traces have no verified task labels.",
    }


def window_metrics(rows):
    n = len(rows)
    latencies = sorted(r.summary["latency_ms"] for r in rows)
    return {
        "samples": n,
        "failures": sum(r.summary["execution_status"] == "failed" for r in rows),
        "failure_rate": (
            sum(r.summary["execution_status"] == "failed" for r in rows) / n
            if n
            else None
        ),
        "p95_latency_ms": latencies[math.ceil(0.95 * n) - 1] if n else None,
    }


async def admit(db, tenant, trace, settings):
    payload = minimize(trace, settings.monitor_capture_payloads)
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()
    async with queue_lock:
        existing = (
            await db.execute(
                select(MonitorTrace).where(
                    MonitorTrace.tenant == tenant,
                    MonitorTrace.external_id == str(trace.trace_id),
                )
            )
        ).scalar_one_or_none()
        if existing:
            if existing.fingerprint != fingerprint:
                raise HTTPException(
                    409, "Trace ID already used with different retained content"
                )
            return {"id": existing.id, "status": existing.status, "duplicate": True}
        counter = await db.get(MonitorTenant, tenant)
        if counter is None:
            counter = MonitorTenant(
                tenant=tenant, accepted=0, sampled_out=0, rejected=0, dropped_spans=0
            )
            db.add(counter)
        # Deterministic head sampling; counts refer to submissions, not unique IDs.
        value = (
            int(hashlib.sha256(f"{tenant}:{trace.trace_id}".encode()).hexdigest(), 16)
            / 2**256
        )
        if value >= settings.monitor_sample_rate:
            counter.sampled_out += 1
            counter.dropped_spans += len(trace.spans)
            await db.commit()
            return {"id": None, "status": "sampled_out", "duplicate": False}
        count = await db.scalar(
            select(func.count())
            .select_from(MonitorTrace)
            .where(MonitorTrace.status == "queued")
        )
        if count >= settings.monitor_queue_capacity:
            counter.rejected += 1
            counter.dropped_spans += len(trace.spans)
            await db.commit()
            raise HTTPException(
                429, "Monitoring queue full; retry with the same trace ID"
            )
        row = MonitorTrace(
            id=str(uuid4()),
            tenant=tenant,
            external_id=str(trace.trace_id),
            fingerprint=fingerprint,
            payload=payload,
            status="queued",
        )
        db.add(row)
        counter.accepted += 1
        await db.commit()
        return {"id": row.id, "status": "queued", "duplicate": False}


async def refresh_alerts(db, tenant, settings):
    rows = (
        await db.execute(
            select(MonitorTrace.id, MonitorTrace.summary)
            .where(MonitorTrace.tenant == tenant, MonitorTrace.status == "processed")
            .order_by(MonitorTrace.created_at.desc())
        )
    ).all()
    groups = {}
    for row in rows:
        bucket = groups.setdefault(row.summary["scope"], [])
        if len(bucket) < settings.monitor_window:
            bucket.append(row)
    existing = (
        (
            await db.execute(
                select(MonitorAlert).where(
                    MonitorAlert.tenant == tenant, MonitorAlert.status == "open"
                )
            )
        )
        .scalars()
        .all()
    )
    active = {(a.scope, a.kind): a for a in existing}
    for scope, items in groups.items():
        metrics = window_metrics(items)
        for kind, value, threshold in [
            ("failure_rate", metrics["failure_rate"], settings.monitor_failure_rate),
            ("p95_latency_ms", metrics["p95_latency_ms"], settings.monitor_latency_ms),
        ]:
            eligible = len(items) >= settings.monitor_min_samples
            firing = eligible and value >= threshold
            previous = active.pop((scope, kind), None)
            evidence = {
                **metrics,
                "threshold": threshold,
                "trace_ids": [r.id for r in items],
                "min_samples": settings.monitor_min_samples,
                "window": settings.monitor_window,
                "scope": json.loads(scope),
            }
            if firing:
                if previous:
                    previous.evidence = evidence
                else:
                    db.add(
                        MonitorAlert(
                            tenant=tenant,
                            scope=scope,
                            kind=kind,
                            status="open",
                            evidence=evidence,
                        )
                    )
            elif previous:
                previous.status = "resolved" if eligible else "insufficient_data"
                previous.resolved_at = now()
    for previous in active.values():
        previous.status = "insufficient_data"
        previous.resolved_at = now()


async def process_batch(factory, settings):
    async with queue_lock:
        async with factory() as db:
            cutoff = now() - timedelta(days=settings.monitor_retention_days)
            await db.execute(
                delete(MonitorTrace).where(MonitorTrace.created_at < cutoff)
            )
            await db.execute(
                delete(MonitorAlert).where(MonitorAlert.created_at < cutoff)
            )
            rows = (
                (
                    await db.execute(
                        select(MonitorTrace)
                        .where(MonitorTrace.status == "queued")
                        .order_by(MonitorTrace.created_at)
                        .limit(25)
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                try:
                    row.summary = summarize(row.payload)
                    row.status = "processed"
                except (ValueError, KeyError, TypeError, StopIteration):
                    # Poison rows never block the queue or leak payloads into logs.
                    row.status = "dead_letter"
                    row.summary = {
                        "error": "Invalid persisted trace; processing failed"
                    }
                row.processed_at = now()
            await db.flush()
            tenants = (await db.execute(select(MonitorTenant.tenant))).scalars().all()
            for tenant in tenants:
                await refresh_alerts(db, tenant, settings)
            await db.commit()
            return len(rows)


async def worker(factory, settings, stop, health):
    while not stop.is_set():
        try:
            count = await process_batch(factory, settings)
            health.update(last_success=now().isoformat(), error=None)
        except Exception:
            count = 0
            health["error"] = (
                "Monitoring worker failed; durable queue retained for retry"
            )
        if count == 25:
            await asyncio.sleep(0)
        else:
            try:
                await asyncio.wait_for(stop.wait(), settings.monitor_poll_seconds)
            except TimeoutError:
                pass
