import asyncio
import json
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from fastapi_szumplate.main import create_app
from fastapi_szumplate.middleware import UnhandledErrorMiddleware
from fastapi_szumplate.problems import (
    PROBLEM_MEDIA_TYPE,
    ProblemType,
    domain_error_handler,
    problem_response,
)
from tests.conftest import make_settings

PROBLEM_JSON = PROBLEM_MEDIA_TYPE
JSON = {"Content-Type": "application/json"}


class Payload(BaseModel):
    name: str


class Refused(Exception):
    """Probe domain error."""


REFUSED = ProblemType("probe-refused", "Probe refused", 409)


@pytest.fixture
def probe_app(app: FastAPI) -> FastAPI:
    @app.get("/probe/thing", operation_id="get_probe_thing")
    def get_thing() -> dict[str, str]:
        return {}

    @app.put("/probe/thing", operation_id="put_probe_thing")
    def put_thing() -> dict[str, str]:
        return {}

    @app.get("/probe/limit", operation_id="get_probe_limit")
    def limited(limit: int = Query(le=100)) -> dict[str, int]:
        return {"limit": limit}

    @app.post("/probe/body", operation_id="post_probe_body")
    def post_body(payload: Payload) -> dict[str, str]:
        return {"name": payload.name}

    @app.get("/probe/boom", operation_id="get_probe_boom")
    def boom() -> None:
        raise RuntimeError("internal detail that must not leak")

    @app.get("/probe/auth", operation_id="get_probe_auth")
    def auth() -> None:
        raise HTTPException(401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"})

    @app.get("/probe/refused", operation_id="get_probe_refused")
    def refused() -> None:
        raise Refused("not today")

    app.add_exception_handler(Refused, domain_error_handler({Refused: REFUSED}))
    return app


@pytest.fixture
def probe(probe_app: FastAPI) -> TestClient:
    return TestClient(probe_app, raise_server_exceptions=False)


def body_of(response: Any) -> dict[str, Any]:
    assert response.headers["content-type"] == PROBLEM_JSON
    return dict(response.json())


def test_unknown_path_is_a_404_problem_with_the_request_id(probe: TestClient) -> None:
    response = probe.get("/probe/missing")

    body = body_of(response)
    assert response.status_code == 404
    assert (body["type"], body["title"], body["status"]) == ("about:blank", "Not Found", 404)
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_trailing_slash_is_a_404_not_a_redirect(probe: TestClient) -> None:
    response = probe.get("/health/", follow_redirects=False)

    assert response.status_code == 404
    body_of(response)


def test_405_lists_every_method_of_the_path(probe: TestClient) -> None:
    response = probe.delete("/probe/thing")

    assert response.status_code == 405
    assert response.headers["Allow"] == "GET, PUT"
    assert body_of(response)["title"] == "Method Not Allowed"


def test_http_exception_keeps_its_headers(probe: TestClient) -> None:
    response = probe.get("/probe/auth")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert body_of(response)["detail"] == "Bearer token required"


def test_validation_error_names_the_field_and_never_echoes_the_input(probe: TestClient) -> None:
    response = probe.get("/probe/limit", params={"limit": "s3cr3t-value"})

    body = body_of(response)
    assert response.status_code == 422
    assert body["type"] == "urn:problem:fastapi-szumplate:validation-error"
    [issue] = body["errors"]
    assert set(issue) == {"loc", "msg", "type"}
    assert issue["loc"] == ["query", "limit"]
    assert "s3cr3t-value" not in response.text


def test_malformed_json_body_is_a_422_without_the_body(probe: TestClient) -> None:
    response = probe.post(
        "/probe/body",
        content='{"name": "leaky-password"',
        headers={"Content-Type": "application/json"},
    )

    body = body_of(response)
    assert response.status_code == 422
    assert body["errors"][0]["type"] == "json_invalid"
    assert "leaky-password" not in response.text


def test_wrong_body_type_is_a_422_with_loc_msg_type_only(probe: TestClient) -> None:
    response = probe.post("/probe/body", json={"name": 5})

    [issue] = body_of(response)["errors"]
    assert issue["loc"] == ["body", "name"]
    assert set(issue) == {"loc", "msg", "type"}


def test_unhandled_exception_is_a_generic_500_problem(probe: TestClient) -> None:
    response = probe.get("/probe/boom")

    body = body_of(response)
    assert response.status_code == 500
    assert body["title"] == "Internal Server Error"
    assert "internal detail" not in response.text


def test_domain_error_gets_its_own_type_and_is_logged_as_a_warning(
    probe_app: FastAPI, capsys: pytest.CaptureFixture[str]
) -> None:
    response = TestClient(probe_app).get("/probe/refused")

    body = body_of(response)
    assert response.status_code == 409
    assert body["type"] == "urn:problem:fastapi-szumplate:probe-refused"
    assert body["title"] == "Probe refused"
    assert body["detail"] == "not today"
    refusals = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if '"request_refused"' in line
    ]
    assert refusals
    assert refusals[0]["level"] == "warning"
    assert "exception" not in refusals[0]


def test_problem_response_documents_each_type_slug() -> None:
    entry = problem_response(REFUSED)

    assert "`probe-refused`" in entry["description"]
    assert entry["content"] == {PROBLEM_JSON: {}}


def test_an_unhandled_error_still_carries_the_cors_headers_and_the_request_id() -> None:
    origin = "https://app.example.com"
    app = create_app(make_settings(cors_origins=[origin]))

    @app.get("/probe/boom", operation_id="get_probe_boom_cors")
    def boom() -> None:
        raise RuntimeError("internal detail that must not leak")

    response = TestClient(app, raise_server_exceptions=False).get(
        "/probe/boom", headers={"Origin": origin}
    )

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_an_exception_after_the_response_started_is_not_swallowed() -> None:
    async def half_a_response(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("broke after the headers were sent")

    client = TestClient(UnhandledErrorMiddleware(half_a_response))

    with pytest.raises(RuntimeError, match="after the headers"):
        client.get("/")


def test_a_websocket_scope_passes_through_the_unhandled_error_middleware() -> None:
    seen: list[str] = []

    async def record(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    asyncio.run(UnhandledErrorMiddleware(record)({"type": "websocket"}, _no_receive, _no_send))

    assert seen == ["websocket"]


async def _no_receive() -> Message:
    return {"type": "websocket.disconnect"}


async def _no_send(_message: Message) -> None:
    return None


def test_json_with_an_integer_beyond_the_parser_limit_is_a_422_but_invalid_utf8_stays_400(
    probe: TestClient,
) -> None:
    long_integer = b'{"name": ' + b"9" * 5000 + b"}"

    too_long = probe.post("/probe/body", content=long_integer, headers=JSON)
    not_text = probe.post("/probe/body", content=b'{"name": "\xff"}', headers=JSON)

    assert (too_long.status_code, too_long.json()["errors"][0]["loc"]) == (422, ["body"])
    assert "9999" not in too_long.text
    assert not_text.status_code == 400


def test_a_failure_in_the_outermost_middleware_is_still_a_500_problem() -> None:
    app = create_app(make_settings())

    class Broken:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            raise RuntimeError("middleware failed")

    app.add_middleware(Broken)

    response = TestClient(app, raise_server_exceptions=False).get("/health")

    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_JSON
    assert "middleware failed" not in response.text
