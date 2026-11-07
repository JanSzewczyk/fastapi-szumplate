"""Request context: request id, bound log context and one access-log line per request."""

import re
import time
import uuid
from typing import Final

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER: Final = "X-Request-ID"
_VALID_REQUEST_ID: Final = re.compile(r"[A-Za-z0-9._-]{1,64}")

log = structlog.get_logger(__name__)


def new_request_id() -> str:
    """Return a fresh, time-ordered request id."""
    return str(uuid.uuid7())


def accept_request_id(candidate: str | None) -> str:
    """Return the inbound id if it is safe to log and echo, otherwise a new one."""
    if candidate is not None and _VALID_REQUEST_ID.fullmatch(candidate):
        return candidate
    return new_request_id()


class RequestContextMiddleware:
    """Pure ASGI middleware, so context variables reach the handlers in the same task."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the next ASGI application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Bind the request id, echo it in the response and log the finished request."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = accept_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        scope.setdefault("state", {})["request_id"] = request_id

        status = 500  # stays 500 when the exception escapes before any response is sent
        started = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            route = getattr(scope.get("route"), "path", None)
            fields = {
                "method": scope["method"],
                "route": route or "unmatched",
                "status": status,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            }
            if status >= 500:
                log.error("request_completed", **fields)
            else:
                log.info("request_completed", **fields)
