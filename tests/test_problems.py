import json
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel

from fastapi_szumplate.problems import (
    PROBLEM_MEDIA_TYPE,
    ProblemType,
    domain_error_handler,
    problem_response,
)

PROBLEM_JSON = PROBLEM_MEDIA_TYPE


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
