"""Request correlation, security headers, access logging and the last-resort error handler."""

import json
import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_body
from app.core.logging import request_id_var

logger = logging.getLogger("coursepilot.access")

# A client-supplied ID ends up in logs, so anything unusual is replaced rather than trusted.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


# The interactive API docs load their scripts from a CDN, so they cannot have the strict policy.
_DOCS_PATHS = ("/docs", "/redoc")
_HSTS = "max-age=31536000; includeSubDomains"


def _secure(headers: MutableHeaders, path: str, hsts: bool) -> None:
    """Headers that cost nothing and close off whole classes of attack."""
    headers.setdefault("X-Content-Type-Options", "nosniff")  # No guessing JSON is a page.
    headers.setdefault("Referrer-Policy", "no-referrer")
    headers.setdefault("X-Frame-Options", "DENY")  # The API is never framed.
    if not path.startswith(_DOCS_PATHS):
        headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    if path.startswith("/api/"):
        # Answers carry a student's private data, so no browser or proxy should keep a copy.
        headers.setdefault("Cache-Control", "no-store")
    if hsts:
        headers.setdefault("Strict-Transport-Security", _HSTS)


class RequestContextMiddleware:
    """Pure ASGI middleware, so that the request ID is still available for unhandled errors."""

    def __init__(self, app: ASGIApp, hsts: bool = False) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied = Headers(scope=scope).get("x-request-id", "")
        request_id = supplied if _SAFE_REQUEST_ID.match(supplied) else uuid.uuid4().hex
        token = request_id_var.set(request_id)

        started = time.perf_counter()
        status = 500
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                _secure(headers, scope["path"], self.hsts)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            # Logged in full here; the client only ever receives a generic message.
            logger.exception("unhandled_exception")
            if not response_started:
                body = error_body("internal_error", "Something went wrong on our side.")
                await send_with_request_id(
                    {
                        "type": "http.response.start",
                        "status": 500,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send_with_request_id(
                    {"type": "http.response.body", "body": json.dumps(body).encode()}
                )
        finally:
            # The path only: query strings can contain data that should not reach logs.
            logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id_var.reset(token)
