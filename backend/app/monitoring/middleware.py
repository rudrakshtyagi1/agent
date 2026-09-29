"""Bound request bytes before JSON parsing; hide legacy unscoped demo APIs."""

import logging
from fastapi.responses import JSONResponse


class MonitoringBoundary:
    def __init__(self, app, settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        prefix = self.settings.api_v1_prefix + "/monitoring"
        monitor = path == prefix or path.startswith(prefix + "/")
        if (
            self.settings.app_env != "development"
            and path not in ("/health", "/health/", "/ready", "/ready/")
            and not monitor
        ):
            return await JSONResponse(
                {"error": "Demo endpoints are disabled outside development"},
                status_code=404,
            )(scope, receive, send)
        if monitor and scope["method"] == "POST":
            chunks = []
            size = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > 524288:
                    return await JSONResponse(
                        {"error": "Trace payload exceeds 512 KiB"}, status_code=413
                    )(scope, receive, send)
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            sent = False

            async def buffered():
                nonlocal sent
                if not sent:
                    sent = True
                    return {
                        "type": "http.request",
                        "body": b"".join(chunks),
                        "more_body": False,
                    }
                return await receive()

            return await self.protected(scope, buffered, send)
        if monitor:
            return await self.protected(scope, receive, send)
        return await self.app(scope, receive, send)

    async def protected(self, scope, receive, send):
        started = False

        async def safe_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, safe_send)
        except Exception:
            # SQL driver exceptions can contain bound telemetry. Do not re-raise
            # into the server's traceback logger or include exception strings.
            logging.getLogger(__name__).error(
                "Monitoring request failed; telemetry details suppressed"
            )
            if not started:
                await JSONResponse(
                    {"error": "Internal monitoring error"}, status_code=500
                )(scope, receive, send)
