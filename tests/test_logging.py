import json
import logging
from typing import Any, Literal
from unittest.mock import patch

import pytest
import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_szumplate import __main__ as entry_point
from fastapi_szumplate.logging_config import _HANDLER_TAG, configure_logging
from fastapi_szumplate.main import create_app
from tests.conftest import make_settings


def lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    out = capsys.readouterr().out
    parsed = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
    return [line for line in parsed if not line["logger"].startswith("httpx")]  # test client noise


@pytest.fixture
def json_app() -> FastAPI:
    return create_app(make_settings(log_format="json"))


def test_json_line_has_the_fixed_fields(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(make_settings(log_format="json"))

    structlog.get_logger("probe").info("order_processed", order_id=7)

    [line] = lines(capsys)
    assert line["event"] == "order_processed"
    assert line["order_id"] == 7
    assert line["level"] == "info"
    assert line["logger"] == "probe"
    assert line["timestamp"].endswith("Z")


def test_console_format_is_readable(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(make_settings(log_format="console"))

    structlog.get_logger("probe").info("order_processed", order_id=7)

    out = capsys.readouterr().out
    assert "order_processed" in out
    assert not out.lstrip().startswith("{")


def test_sensitive_keys_are_masked_also_when_nested(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(make_settings(log_format="json"))

    structlog.get_logger("probe").info(
        "login", password="hunter2", headers={"Authorization": "Bearer abc", "accept": "*/*"}
    )

    [line] = lines(capsys)
    assert line["password"] == "***"
    assert line["headers"] == {"Authorization": "***", "accept": "*/*"}


def test_configure_logging_is_idempotent() -> None:
    settings = make_settings(log_format="json")

    configure_logging(settings)
    configure_logging(settings)

    tagged = [h for h in logging.getLogger().handlers if getattr(h, _HANDLER_TAG, False)]
    assert len(tagged) == 1


def test_stdlib_records_share_the_pipeline(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(make_settings(log_format="json"))

    logging.getLogger("uvicorn.error").warning("worker %s restarted", 3)

    [line] = lines(capsys)
    assert line["event"] == "worker 3 restarted"
    assert line["logger"] == "uvicorn.error"
    assert line["level"] == "warning"


def test_log_level_filters_records(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(make_settings(log_format="json", log_level="WARNING"))

    structlog.get_logger("probe").info("too_quiet")

    assert lines(capsys) == []


def test_request_is_logged_once_with_the_route_template(
    json_app: FastAPI, capsys: pytest.CaptureFixture[str]
) -> None:
    @json_app.get("/things/{thing_id}", operation_id="get_thing_probe")
    def get_thing(thing_id: int) -> dict[str, int]:
        return {"id": thing_id}

    response = TestClient(json_app).get("/things/42", headers={"X-Request-ID": "abc-123"})

    [line] = lines(capsys)
    assert response.headers["X-Request-ID"] == "abc-123"
    assert line["event"] == "request_completed"
    assert line["request_id"] == "abc-123"
    assert (line["method"], line["route"], line["status"]) == ("GET", "/things/{thing_id}", 200)
    assert line["duration_ms"] >= 0


@pytest.mark.parametrize(
    "inbound",
    ["has space", "x" * 65, "back\\slash", "semi;colon"],
    ids=["space", "too-long", "backslash", "separator"],
)
def test_unsafe_inbound_request_id_is_replaced(
    json_app: FastAPI, capsys: pytest.CaptureFixture[str], inbound: str
) -> None:
    response = TestClient(json_app).get("/health", headers={"X-Request-ID": inbound})

    [line] = lines(capsys)
    assert response.headers["X-Request-ID"] != inbound
    assert line["request_id"] == response.headers["X-Request-ID"]


def test_missing_request_id_is_generated_per_request(json_app: FastAPI) -> None:
    client = TestClient(json_app)

    first = client.get("/health").headers["X-Request-ID"]
    second = client.get("/health").headers["X-Request-ID"]

    assert first != second


def test_log_lines_written_by_a_handler_carry_the_request_id(
    json_app: FastAPI, capsys: pytest.CaptureFixture[str]
) -> None:
    @json_app.get("/noisy", operation_id="get_noisy_probe")
    def noisy() -> dict[str, str]:
        structlog.get_logger("probe").info("inside_handler")
        return {}

    response = TestClient(json_app).get("/noisy")

    inside, completed = lines(capsys)
    assert inside["request_id"] == completed["request_id"] == response.headers["X-Request-ID"]


def test_unmatched_path_is_logged_without_the_raw_path(
    json_app: FastAPI, capsys: pytest.CaptureFixture[str]
) -> None:
    TestClient(json_app).get("/nope/123")

    [line] = lines(capsys)
    assert (line["route"], line["status"]) == ("unmatched", 404)


def test_unhandled_error_is_logged_as_status_500(
    json_app: FastAPI, capsys: pytest.CaptureFixture[str]
) -> None:
    @json_app.get("/boom", operation_id="get_boom_probe")
    def boom() -> None:
        raise RuntimeError("secret internals")

    response = TestClient(json_app, raise_server_exceptions=False).get("/boom")

    [line] = lines(capsys)
    assert response.status_code == 500
    assert (line["event"], line["status"], line["level"]) == ("request_completed", 500, "error")


@pytest.mark.parametrize("log_format", ["json", "console"])
def test_a_logged_traceback_keeps_the_frames_but_not_the_local_variables(
    log_format: Literal["json", "console"], capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(make_settings(log_format=log_format))

    def handle_request() -> None:
        headers = {"Authorization": "Bearer sekret-token-1"}  # a local, as ASGI's `scope` is
        raise RuntimeError(f"failed with {len(headers)} header")

    try:
        handle_request()
    except RuntimeError:
        structlog.get_logger("probe").exception("job_failed")

    out = capsys.readouterr().out
    assert "sekret-token-1" not in out
    assert "handle_request" in out
    assert "RuntimeError" in out


def test_cors_is_off_without_origins_and_exposes_the_request_id_with_them() -> None:
    plain = TestClient(create_app(make_settings()))
    cors = TestClient(create_app(make_settings(cors_origins=["https://app.example.com"])))
    origin = {"Origin": "https://app.example.com"}

    assert "access-control-allow-origin" not in plain.get("/health", headers=origin).headers
    allowed = cors.get("/health", headers=origin).headers
    assert allowed["access-control-allow-origin"] == "https://app.example.com"
    assert "X-Request-ID" in allowed["access-control-expose-headers"]
    assert "access-control-allow-credentials" not in allowed


def test_entry_point_starts_uvicorn_with_our_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "9100")
    with patch.object(uvicorn, "run", autospec=True) as run:
        entry_point.main()

    run.assert_called_once()
    assert run.call_args.args == ("fastapi_szumplate.main:create_app",)
    kwargs = run.call_args.kwargs
    assert kwargs["factory"] is True
    assert kwargs["port"] == 9100
    assert kwargs["log_config"] is None
    assert kwargs["access_log"] is False
