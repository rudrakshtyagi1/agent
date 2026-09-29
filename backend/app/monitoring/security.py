"""Key-derived tenancy and payload minimization before durable storage."""

import re
import math
import secrets
from fastapi import Header, HTTPException
from app.config import get_settings

SECRET_KEY = re.compile(
    r"password|secret|token|authorization|api.?key|cookie|email|phone|address|ssn", re.I
)
EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
BEARER = re.compile(
    r"(?i)\bBearer\s+\S+|\bsk-[\w-]+|\b(?:api[_-]?key|password|secret|token)\s*[=:]\s*[^\s,;]+"
)
PHONE = re.compile(r"(?<!\w)\+?\d[\d ()-]{7,}\d(?!\w)")


def scrub(value, depth=0):
    if depth > 12:
        return "[DEPTH LIMIT]"
    if isinstance(value, dict):
        return {
            scrub(str(k), depth + 1): (
                "[REDACTED]" if SECRET_KEY.search(str(k)) else scrub(v, depth + 1)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [scrub(v, depth + 1) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return "[NONFINITE]"
    if isinstance(value, str):
        return PHONE.sub(
            "[REDACTED]", BEARER.sub("[REDACTED]", EMAIL.sub("[REDACTED]", value))
        )
    return value


def minimize(trace, capture):
    payload = trace.model_dump(mode="json")
    # Scrub text only, preserving IDs, timestamps and structured numeric fields.
    for field in ("agent_name", "agent_version"):
        payload[field] = scrub(payload[field])
    for span in payload["spans"]:
        span["name"] = scrub(span["name"])
        for field in ("input", "output", "metadata"):
            span[field] = (
                scrub(span[field]) if capture else None if field != "metadata" else {}
            )
        span["error"] = (
            (scrub(span["error"]) if capture else "Reported span error")
            if span["error"]
            else None
        )
    return payload


def validate_keys(settings):
    if settings.app_env != "development" and not settings.monitor_keys:
        raise ValueError("MONITOR_KEYS is required outside development")
    if any(
        not key or len(key) > 128 or len(value) < 32
        for key, value in settings.monitor_keys.items()
    ):
        raise ValueError(
            "Each monitor tenant needs a nonempty name and a key of at least 32 characters"
        )
    if len(set(settings.monitor_keys.values())) != len(settings.monitor_keys):
        raise ValueError("Monitor keys must be unique per tenant")
    if settings.monitor_min_samples > settings.monitor_window:
        raise ValueError("Monitor minimum samples cannot exceed the window")


async def tenant(authorization: str | None = Header(default=None)):
    settings = get_settings()
    if not settings.monitor_keys and settings.app_env == "development":
        return "local-demo"
    token = (
        authorization[7:]
        if authorization and authorization.startswith("Bearer ")
        else ""
    )
    for name, key in settings.monitor_keys.items():
        if secrets.compare_digest(token.encode(), key.encode()):
            return name
    raise HTTPException(401, "Valid monitoring bearer key required")
