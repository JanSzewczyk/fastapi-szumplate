from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.library.factories import book_payload, isbn_for

PROBLEM = "application/problem+json"
MISSING_ID = "0192f5e0-5a3b-7c11-9d2e-3f6a1b2c4d5e"


def create_book(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post("/v1/books", json=book_payload(**overrides))
    assert response.status_code == 201
    return dict(response.json())


def test_create_returns_201_with_the_book_and_a_location(api: TestClient) -> None:
    response = api.post(
        "/v1/books",
        json={"isbn": isbn_for(1), "title": "Clean Code", "author": "R. Martin", "copies": 3},
    )

    body = response.json()
    assert response.status_code == 201
    assert response.headers["Location"] == f"/v1/books/{body['id']}"
    assert {k: body[k] for k in ("isbn", "title", "author", "copies")} == {
        "isbn": isbn_for(1),
        "title": "Clean Code",
        "author": "R. Martin",
        "copies": 3,
    }


def test_created_book_can_be_fetched(api: TestClient) -> None:
    book = create_book(api, title="Refactoring")

    response = api.get(f"/v1/books/{book['id']}")

    assert response.status_code == 200
    assert response.json() == book


def test_duplicate_isbn_is_a_409_with_its_own_type(api: TestClient) -> None:
    create_book(api, isbn=isbn_for(9))

    response = api.post("/v1/books", json=book_payload(isbn=isbn_for(9)))

    assert response.status_code == 409
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["type"] == "urn:problem:fastapi-szumplate:isbn-already-exists"


def test_unknown_book_is_a_404_problem(api: TestClient) -> None:
    response = api.get(f"/v1/books/{MISSING_ID}")

    assert response.status_code == 404
    assert response.json()["type"] == "urn:problem:fastapi-szumplate:book-not-found"
    assert response.headers["content-type"] == PROBLEM


def test_update_changes_title_and_author(api: TestClient) -> None:
    book = create_book(api, copies=2)

    response = api.put(f"/v1/books/{book['id']}", json={"title": "New", "author": "Other"})

    assert response.status_code == 200
    assert response.json() == {**book, "title": "New", "author": "Other"}
    assert api.get(f"/v1/books/{book['id']}").json()["title"] == "New"


def test_update_of_an_unknown_book_is_a_404(api: TestClient) -> None:
    response = api.put(f"/v1/books/{MISSING_ID}", json={"title": "T", "author": "A"})

    assert response.status_code == 404


def test_list_is_paged_and_reports_the_total(api: TestClient) -> None:
    for number in range(1, 6):
        create_book(api, isbn=isbn_for(number))

    response = api.get("/v1/books", params={"limit": 2, "offset": 2})

    body = response.json()
    assert response.status_code == 200
    assert (body["total"], body["limit"], body["offset"]) == (5, 2, 2)
    assert [b["isbn"] for b in body["items"]] == [isbn_for(3), isbn_for(4)]


def test_list_uses_the_configured_page_size_by_default(api: TestClient) -> None:
    body = api.get("/v1/books").json()

    assert body == {"items": [], "total": 0, "limit": 20, "offset": 0}


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/v1/books", {"isbn": "123", "title": "T", "author": "A", "copies": 1}),
        ("post", "/v1/books", {"isbn": isbn_for(1), "title": "", "author": "A", "copies": 1}),
        ("post", "/v1/books", {"isbn": isbn_for(1), "title": "T", "author": "A", "copies": 0}),
        ("post", "/v1/books", {"isbn": isbn_for(1), "title": "T", "author": "A", "copies": "3"}),
        ("post", "/v1/books", {"isbn": isbn_for(1), "title": "T", "author": "A", "copies": 1.0}),
        ("post", "/v1/books", {"isbn": isbn_for(1), "title": "T", "author": "A"}),
        (
            "post",
            "/v1/books",
            {"isbn": isbn_for(1), "title": "T", "author": "A", "copies": 1, "extra": 1},
        ),
        ("put", f"/v1/books/{MISSING_ID}", {"title": "T"}),
        ("put", "/v1/books/not-a-uuid", {"title": "T", "author": "A"}),
        ("get", "/v1/books/not-a-uuid", None),
        ("get", "/v1/books?limit=0", None),
        ("get", "/v1/books?limit=101", None),
        ("get", "/v1/books?offset=-1", None),
        ("get", "/v1/books?limit=ten", None),
    ],
    ids=[
        "isbn-pattern",
        "empty-title",
        "zero-copies",
        "copies-as-string",
        "copies-as-float",
        "missing-copies",
        "extra-field",
        "update-missing-author",
        "update-bad-uuid",
        "get-bad-uuid",
        "limit-zero",
        "limit-too-big",
        "negative-offset",
        "limit-not-int",
    ],
)
def test_invalid_input_is_a_422_problem(
    api: TestClient, method: str, path: str, payload: dict[str, Any] | None
) -> None:
    response = api.request(method, path, json=payload)

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["type"] == "urn:problem:fastapi-szumplate:validation-error"


def test_wrong_method_is_a_405_with_allow(api: TestClient) -> None:
    response = api.delete("/v1/books")

    assert response.status_code == 405
    assert response.headers["Allow"] == "GET, POST"


def test_unversioned_path_is_a_404(api: TestClient) -> None:
    assert api.get("/books").status_code == 404


def test_access_log_uses_the_full_route_template(
    api: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    api.get(f"/v1/books/{MISSING_ID}")

    assert '"route": "/v1/books/{book_id}"' in capsys.readouterr().out
