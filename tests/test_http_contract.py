"""The HTTP contract through the real application, written from `openapi.json`.

Cross-cutting rules that belong to no single module: every error is Problem Details with its
own type, title and status; every response carries `X-Request-ID`; a wrong method is a 405 with
`Allow`; a trailing slash is a 404; CORS and validation never leak what the client sent.
"""

import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response

from fastapi_szumplate.health.readiness import register_readiness_check
from fastapi_szumplate.main import create_app
from tests.conftest import make_settings
from tests.library.factories import book_payload, isbn_for

PROBLEM = "application/problem+json"
TYPE = "urn:problem:fastapi-szumplate:"
MISSING_ID = "0192f5e0-5a3b-7c11-9d2e-3f6a1b2c4d5e"
JSON_BYTES = {"Content-Type": "application/json"}
REQUEST_ID_SHAPE = re.compile(r"[A-Za-z0-9._-]{1,64}")
PROBLEM_FIELDS = {"type", "title", "status", "detail", "errors", "request_id"}

# Every path of the contract with the methods it documents.
DOCUMENTED_METHODS = {
    "/health": ["GET"],
    "/health/ready": ["GET"],
    "/v1/books": ["GET", "POST"],
    "/v1/books/{book_id}": ["GET", "PUT"],
    "/v1/loans": ["GET", "POST"],
    "/v1/loans/{loan_id}": ["GET"],
    "/v1/loans/{loan_id}/return": ["POST"],
}


def concrete(path: str) -> str:
    return path.replace("{book_id}", MISSING_ID).replace("{loan_id}", MISSING_ID)


def add_book(client: TestClient, number: int = 1, *, copies: int = 1) -> str:
    response = client.post("/v1/books", json=book_payload(isbn=isbn_for(number), copies=copies))
    assert response.status_code == 201
    return str(response.json()["id"])


def borrow(client: TestClient, book_id: str, member_id: str = "member-1") -> Response:
    return client.post("/v1/loans", json={"book_id": book_id, "member_id": member_id})


def raise_inside_a_route(app: FastAPI) -> None:
    @app.get("/probe/boom", operation_id="get_probe_boom")
    def boom() -> None:
        raise RuntimeError("internal detail that must not leak")


# Each sender builds the state it needs and returns the response that carries the error.
type Sender = Callable[[TestClient, FastAPI], Response]


def send_unreadable_body(client: TestClient, app: FastAPI) -> Response:
    return client.post("/v1/books", content=b"\xff\xfe\x00", headers=JSON_BYTES)


def send_unknown_path(client: TestClient, app: FastAPI) -> Response:
    return client.get("/no/such/path")


def send_unknown_book(client: TestClient, app: FastAPI) -> Response:
    return client.get(f"/v1/books/{MISSING_ID}")


def send_update_of_unknown_book(client: TestClient, app: FastAPI) -> Response:
    return client.put(f"/v1/books/{MISSING_ID}", json={"title": "T", "author": "A"})


def send_unknown_loan(client: TestClient, app: FastAPI) -> Response:
    return client.get(f"/v1/loans/{MISSING_ID}")


def send_return_of_unknown_loan(client: TestClient, app: FastAPI) -> Response:
    return client.post(f"/v1/loans/{MISSING_ID}/return")


def send_loan_of_unknown_book(client: TestClient, app: FastAPI) -> Response:
    return borrow(client, MISSING_ID)


def send_wrong_method(client: TestClient, app: FastAPI) -> Response:
    return client.delete("/v1/books")


def send_duplicate_isbn(client: TestClient, app: FastAPI) -> Response:
    add_book(client, 1)
    return client.post("/v1/books", json=book_payload(isbn=isbn_for(1)))


def send_already_borrowed(client: TestClient, app: FastAPI) -> Response:
    book_id = add_book(client, 1, copies=2)
    borrow(client, book_id)
    return borrow(client, book_id)


def send_member_over_the_limit(client: TestClient, app: FastAPI) -> Response:
    for number in range(1, 4):
        borrow(client, add_book(client, number))
    return borrow(client, add_book(client, 4))


def send_no_free_copy(client: TestClient, app: FastAPI) -> Response:
    book_id = add_book(client, 1)
    borrow(client, book_id, "member-1")
    return borrow(client, book_id, "member-2")


def send_second_return(client: TestClient, app: FastAPI) -> Response:
    loan = borrow(client, add_book(client, 1)).json()
    client.post(f"/v1/loans/{loan['id']}/return")
    return client.post(f"/v1/loans/{loan['id']}/return")


def send_return_before_borrow(client: TestClient, app: FastAPI) -> Response:
    loan = borrow(client, add_book(client, 1)).json()
    return client.post(f"/v1/loans/{loan['id']}/return", json={"returned_on": "2000-01-01"})


def send_invalid_query(client: TestClient, app: FastAPI) -> Response:
    return client.get("/v1/books", params={"limit": 0})


def send_when_not_ready(client: TestClient, app: FastAPI) -> Response:
    def broken() -> None:
        raise ConnectionError("db password is hunter2")

    register_readiness_check(app, "database", broken)
    return client.get("/health/ready")


def send_when_the_server_fails(client: TestClient, app: FastAPI) -> Response:
    raise_inside_a_route(app)
    return client.get("/probe/boom")


ERROR_CASES = [
    pytest.param(send_unreadable_body, 400, "about:blank", "Bad Request", id="400-unreadable-body"),
    pytest.param(send_unknown_path, 404, "about:blank", "Not Found", id="404-unknown-path"),
    pytest.param(
        send_unknown_book, 404, f"{TYPE}book-not-found", "Book not found", id="404-get-book"
    ),
    pytest.param(
        send_update_of_unknown_book,
        404,
        f"{TYPE}book-not-found",
        "Book not found",
        id="404-update-book",
    ),
    pytest.param(
        send_loan_of_unknown_book,
        404,
        f"{TYPE}book-not-found",
        "Book not found",
        id="404-lend-unknown-book",
    ),
    pytest.param(
        send_unknown_loan, 404, f"{TYPE}loan-not-found", "Loan not found", id="404-get-loan"
    ),
    pytest.param(
        send_return_of_unknown_loan,
        404,
        f"{TYPE}loan-not-found",
        "Loan not found",
        id="404-return-loan",
    ),
    pytest.param(
        send_wrong_method, 405, "about:blank", "Method Not Allowed", id="405-wrong-method"
    ),
    pytest.param(
        send_duplicate_isbn,
        409,
        f"{TYPE}isbn-already-exists",
        "ISBN already exists",
        id="409-isbn-already-exists",
    ),
    pytest.param(
        send_already_borrowed,
        409,
        f"{TYPE}already-borrowed",
        "Member already has this book",
        id="409-already-borrowed",
    ),
    pytest.param(
        send_member_over_the_limit,
        409,
        f"{TYPE}member-limit-reached",
        "Member loan limit reached",
        id="409-member-limit-reached",
    ),
    pytest.param(
        send_no_free_copy, 409, f"{TYPE}no-free-copy", "No free copy", id="409-no-free-copy"
    ),
    pytest.param(
        send_second_return,
        409,
        f"{TYPE}loan-already-returned",
        "Loan already returned",
        id="409-loan-already-returned",
    ),
    pytest.param(
        send_return_before_borrow,
        409,
        f"{TYPE}returned-before-borrowed",
        "Returned before it was borrowed",
        id="409-returned-before-borrowed",
    ),
    pytest.param(
        send_invalid_query,
        422,
        f"{TYPE}validation-error",
        "Request validation failed",
        id="422-validation-error",
    ),
    pytest.param(
        send_when_not_ready,
        503,
        f"{TYPE}service-not-ready",
        "Service not ready",
        id="503-service-not-ready",
    ),
    pytest.param(
        send_when_the_server_fails,
        500,
        "about:blank",
        "Internal Server Error",
        id="500-unhandled-exception",
    ),
]


@pytest.fixture
def lenient(app: FastAPI) -> Iterator[TestClient]:
    """A client that gets the 500 response instead of the re-raised exception."""
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.mark.parametrize(("send", "status", "type_", "title"), ERROR_CASES)
def test_every_error_is_problem_details_with_its_own_type_title_and_status(
    send: Sender, status: int, type_: str, title: str, app: FastAPI, lenient: TestClient
) -> None:
    response = send(lenient, app)

    body = response.json()
    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM
    assert (body["type"], body["title"], body["status"]) == (type_, title, status)
    assert isinstance(body["detail"], str)
    assert set(body) <= PROBLEM_FIELDS
    assert ("errors" in body) == (status == 422)


@pytest.mark.parametrize(("send", "status", "type_", "title"), ERROR_CASES)
def test_every_error_carries_the_request_id_in_the_header_and_the_body(
    send: Sender, status: int, type_: str, title: str, app: FastAPI, lenient: TestClient
) -> None:
    """Defect 1 is the 500 case: the body names a request id the response header lacks."""
    response = send(lenient, app)

    header = response.headers.get("X-Request-ID")
    assert header is not None, f"{status} has no X-Request-ID header"
    assert REQUEST_ID_SHAPE.fullmatch(header)
    assert response.json()["request_id"] == header


@pytest.mark.parametrize(("send", "status", "type_", "title"), ERROR_CASES)
def test_a_supplied_request_id_is_echoed_by_every_error(
    send: Sender, status: int, type_: str, title: str, app: FastAPI
) -> None:
    """Defect 1 is the 500 case: the header is missing although the body carries the id."""
    with TestClient(
        app, raise_server_exceptions=False, headers={"X-Request-ID": "client-id-7"}
    ) as client:
        response = send(client, app)

    assert response.headers.get("X-Request-ID") == "client-id-7"
    assert response.json()["request_id"] == "client-id-7"


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("GET", "/health", 200),
        ("GET", "/health/ready", 200),
        ("GET", "/v1/books", 200),
        ("GET", "/v1/loans", 200),
        ("POST", "/v1/books", 201),
    ],
    ids=["health", "ready", "list-books", "list-loans", "create-book"],
)
def test_successful_responses_carry_a_request_id_too(
    client: TestClient, method: str, path: str, expected: int
) -> None:
    response = client.request(method, path, json=book_payload() if method == "POST" else None)

    assert response.status_code == expected
    assert REQUEST_ID_SHAPE.fullmatch(response.headers["X-Request-ID"])


def test_a_request_id_of_exactly_64_characters_is_echoed(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "a" * 64})

    assert response.headers["X-Request-ID"] == "a" * 64


@pytest.mark.parametrize(
    "inbound",
    [b"", b"id\twith\ttab", b"\xfc\xf1", b"a/b", b"a" * 65],
    ids=["empty", "tab", "non-ascii", "slash", "too-long"],
)
def test_an_unsafe_request_id_is_replaced_on_an_error_too(
    client: TestClient, inbound: bytes
) -> None:
    response = client.get("/no/such/path", headers={b"X-Request-ID": inbound})

    header = response.headers["X-Request-ID"]
    assert header.encode() != inbound
    assert REQUEST_ID_SHAPE.fullmatch(header)
    assert response.json()["request_id"] == header


def test_the_table_of_methods_in_this_file_is_the_contract(app: FastAPI) -> None:
    paths = app.openapi()["paths"]

    documented = {path: sorted(method.upper() for method in item) for path, item in paths.items()}
    assert documented == DOCUMENTED_METHODS


UNDOCUMENTED = [
    pytest.param(path, method, id=f"{method} {path}")
    for path, allowed in DOCUMENTED_METHODS.items()
    for method in ("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD")
    if method not in allowed
]


@pytest.mark.parametrize(("path", "method"), UNDOCUMENTED)
def test_a_method_the_path_does_not_have_is_a_405_listing_the_ones_it_has(
    client: TestClient, path: str, method: str
) -> None:
    response = client.request(method, concrete(path))

    allow = {m.strip() for m in response.headers["Allow"].split(",")}
    assert response.status_code == 405
    assert allow == set(DOCUMENTED_METHODS[path])
    if method != "HEAD":  # a HEAD answer has no body by definition
        assert response.headers["content-type"] == PROBLEM
        assert response.json()["title"] == "Method Not Allowed"


@pytest.mark.parametrize("path", sorted(DOCUMENTED_METHODS))
def test_a_trailing_slash_is_a_404_problem_not_a_redirect(client: TestClient, path: str) -> None:
    method = DOCUMENTED_METHODS[path][0]

    response = client.request(method, concrete(path) + "/", follow_redirects=False)

    assert response.status_code == 404
    assert "location" not in response.headers
    assert response.headers["content-type"] == PROBLEM


@pytest.mark.parametrize(
    "path", ["/", "/v1", "/v2/books", "/books", "/health/live", "/v1/books/x/y", "/v1/loans/x/y/z"]
)
def test_an_unknown_path_is_a_404_problem(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM


def test_a_validation_error_never_echoes_what_the_client_sent(client: TestClient) -> None:
    secret = "s3cr3t-hunter2"
    payloads = [
        {"isbn": secret, "title": secret, "author": secret, "copies": secret},
        {"isbn": isbn_for(1), "title": "T", "author": "A", "copies": 1, "password": secret},
        {"isbn": isbn_for(1), "title": "x" * 201, "author": "A", "copies": 1},
    ]

    for payload in payloads:
        response = client.post("/v1/books", json=payload)

        assert response.status_code == 422
        assert secret not in response.text
        assert "x" * 201 not in response.text
        for issue in response.json()["errors"]:
            assert set(issue) == {"loc", "msg", "type"}
            assert issue["loc"][0] == "body"


def test_a_validation_error_in_the_path_or_query_never_echoes_the_value(
    client: TestClient,
) -> None:
    for response in (
        client.get("/v1/books/s3cr3t-hunter2"),
        client.get("/v1/loans", params={"active": "s3cr3t-hunter2"}),
        client.get("/v1/loans", params={"limit": "s3cr3t-hunter2", "offset": "s3cr3t-hunter2"}),
    ):
        assert response.status_code == 422
        assert "s3cr3t-hunter2" not in response.text


def test_a_path_validation_error_names_the_parameter(
    client: TestClient,
) -> None:
    assert client.get("/v1/books/not-a-uuid").json()["errors"][0]["loc"] == ["path", "book_id"]


class TestCors:
    ORIGIN = "https://app.example.com"

    @pytest.fixture
    def cors(self) -> Iterator[TestClient]:
        app = create_app(make_settings(cors_origins=[self.ORIGIN]))
        with TestClient(app) as test_client:
            yield test_client

    @pytest.mark.parametrize(
        ("method", "path", "status"),
        [("GET", "/v1/books/" + MISSING_ID, 404), ("GET", "/v1/books?limit=0", 422)],
        ids=["404", "422"],
    )
    def test_error_responses_carry_the_cors_headers(
        self, cors: TestClient, method: str, path: str, status: int
    ) -> None:
        response = cors.request(method, path, headers={"Origin": self.ORIGIN})

        assert response.status_code == status
        assert response.headers["access-control-allow-origin"] == self.ORIGIN
        assert "X-Request-ID" in response.headers["access-control-expose-headers"]
        assert response.headers["content-type"] == PROBLEM

    def test_an_origin_outside_the_list_gets_no_cors_headers(self, cors: TestClient) -> None:
        response = cors.get("/health", headers={"Origin": "https://evil.example.com"})

        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers

    def test_a_preflight_allows_only_the_declared_methods_and_no_credentials(
        self, cors: TestClient
    ) -> None:
        response = cors.options(
            "/v1/books",
            headers={
                "Origin": self.ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        allowed = {m.strip() for m in response.headers["access-control-allow-methods"].split(",")}
        assert response.status_code == 200
        assert "PATCH" not in allowed
        assert {"GET", "POST", "PUT"} <= allowed
        assert "access-control-allow-credentials" not in response.headers
        assert response.headers["access-control-allow-origin"] == self.ORIGIN

    @pytest.mark.parametrize(
        "headers",
        [
            {"Access-Control-Request-Method": "PATCH"},
            {"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"},
            {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-evil"},
        ],
        ids=["method", "origin", "header"],
    )
    def test_a_refused_preflight_is_a_400(self, cors: TestClient, headers: dict[str, str]) -> None:
        response = cors.options("/v1/books", headers={"Origin": self.ORIGIN, **headers})

        assert response.status_code == 400

    def test_without_cors_a_preflight_is_a_405_problem(self, client: TestClient) -> None:
        response = client.options(
            "/v1/books",
            headers={"Origin": self.ORIGIN, "Access-Control-Request-Method": "POST"},
        )

        assert response.status_code == 405
        assert response.headers["content-type"] == PROBLEM


def test_a_failed_readiness_check_does_not_leak_into_other_routes(
    app: FastAPI, client: TestClient
) -> None:
    def broken() -> None:
        raise ConnectionError("db password is hunter2")

    register_readiness_check(app, "database", broken)

    assert client.get("/health/ready").status_code == 503
    assert client.get("/health").status_code == 200
    assert client.get("/v1/books").status_code == 200


def test_readiness_names_every_failed_check_sorted_and_the_passing_ones_are_not_listed(
    app: FastAPI, client: TestClient
) -> None:
    def broken() -> None:
        raise ConnectionError("hunter2")

    register_readiness_check(app, "queue", broken)
    register_readiness_check(app, "cache", lambda: None)
    register_readiness_check(app, "database", broken)

    body = client.get("/health/ready").json()

    assert body["detail"] == "Not ready: database, queue"
    assert "hunter2" not in str(body)


def test_the_health_payloads_are_exactly_the_documented_ones(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ready", "checks": {}}


def test_every_success_status_of_the_contract_is_reachable(client: TestClient) -> None:
    """200 and 201 for each operation, in one story, so a documented status never goes dead."""
    book_id = add_book(client, 1, copies=2)
    loan = borrow(client, book_id)

    statuses = {
        "get_health": client.get("/health").status_code,
        "get_readiness": client.get("/health/ready").status_code,
        "list_books": client.get("/v1/books").status_code,
        "get_book": client.get(f"/v1/books/{book_id}").status_code,
        "update_book": client.put(
            f"/v1/books/{book_id}", json={"title": "T", "author": "A"}
        ).status_code,
        "create_loan": loan.status_code,
        "list_loans": client.get("/v1/loans").status_code,
        "get_loan": client.get(f"/v1/loans/{loan.json()['id']}").status_code,
        "return_loan": client.post(f"/v1/loans/{loan.json()['id']}/return").status_code,
    }

    assert statuses == {
        "get_health": 200,
        "get_readiness": 200,
        "list_books": 200,
        "get_book": 200,
        "update_book": 200,
        "create_loan": 201,
        "list_loans": 200,
        "get_loan": 200,
        "return_loan": 200,
    }


def test_the_documented_responses_match_the_bodies_the_app_sends(client: TestClient) -> None:
    """A 201 and a 200 body have exactly the fields the schemas name, no more."""
    book = client.post("/v1/books", json=book_payload(isbn=isbn_for(1))).json()
    loan = borrow(client, book["id"]).json()
    page: dict[str, Any] = client.get("/v1/loans").json()

    assert set(book) == {"id", "isbn", "title", "author", "copies"}
    assert set(loan) == {"id", "book_id", "member_id", "borrowed_on", "due_on", "returned_on"}
    assert set(page) == {"items", "total", "limit", "offset"}
    assert set(page["items"][0]) == set(loan)


def test_a_route_outside_the_spec_still_answers_a_wrong_method_with_its_own_allow(
    app: FastAPI, client: TestClient
) -> None:
    @app.get("/internal/ping", include_in_schema=False)
    def ping() -> dict[str, str]:
        return {}

    response = client.post("/internal/ping")

    assert response.status_code == 405
    assert response.headers["Allow"] == "GET"
    assert response.headers["content-type"] == PROBLEM
