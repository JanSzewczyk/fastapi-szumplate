"""Request context: request id, bound log context and one access-log line per request."""

import re
import time
import uuid
from typing import Final

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from fastapi_szumplate.problems import unhandled_problem

REQUEST_ID_HEADER: Final = "X-Request-ID"
_VALID_REQUEST_ID: Final = re.compile(r"[A-Za-z0-9._-]{1,64}")
_UNHANDLED_KEY: Final = "unhandled_exception"

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
        state = scope.setdefault("state", {})
        state["request_id"] = request_id

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
                # The traceback of an unhandled error is logged here, on the one line per request.
                if _UNHANDLED_KEY in state:
                    fields["exc_info"] = state[_UNHANDLED_KEY]
                log.error("request_completed", **fields)
            else:
                log.info("request_completed", **fields)


class UnhandledErrorMiddleware:
    """Answer an exception no handler claimed with the generic 500 problem.

    Starlette's own catch-all runs outside every user middleware, so its response would carry
    neither `X-Request-ID` nor CORS headers. This middleware is the innermost one, so the response
    it sends passes through both. It records the exception in the request state and leaves the
    logging to `RequestContextMiddleware`, so the traceback is logged once and the server does not
    log it again. A response that has already started cannot be replaced: that exception escapes.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the next ASGI application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the application; turn an unhandled exception into a 500 problem."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def track_start(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, track_start)
        except Exception as exc:
            if started:
                raise
            scope.setdefault("state", {})[_UNHANDLED_KEY] = exc
            await unhandled_problem(Request(scope, receive))(scope, receive, send)
