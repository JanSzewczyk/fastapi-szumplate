from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.library.factories import book_payload, isbn_for

PROBLEM = "application/problem+json"
MISSING_ID = "0192f5e0-5a3b-7c11-9d2e-3f6a1b2c4d5e"
TYPE = "urn:problem:fastapi-szumplate:"

pytestmark = pytest.mark.usefixtures("pinned_clock")  # today is 2026-01-06


def add_book(api: TestClient, number: int = 1, *, copies: int = 1) -> str:
    response = api.post("/v1/books", json=book_payload(isbn=isbn_for(number), copies=copies))
    assert response.status_code == 201
    return str(response.json()["id"])


def borrow(api: TestClient, book_id: str, member_id: str = "member-1") -> Any:
    return api.post("/v1/loans", json={"book_id": book_id, "member_id": member_id})


def test_lending_returns_201_a_location_and_the_dates(api: TestClient) -> None:
    book_id = add_book(api)

    response = borrow(api, book_id, "member-1")

    body = response.json()
    assert response.status_code == 201
    assert response.headers["Location"] == f"/v1/loans/{body['id']}"
    assert (body["book_id"], body["member_id"]) == (book_id, "member-1")
    assert (body["borrowed_on"], body["due_on"], body["returned_on"]) == (
        "2026-01-06",
        "2026-01-20",
        None,
    )


def test_lent_loan_can_be_fetched(api: TestClient) -> None:
    loan = borrow(api, add_book(api)).json()

    response = api.get(f"/v1/loans/{loan['id']}")

    assert response.status_code == 200
    assert response.json() == loan


def test_lending_an_unknown_book_is_a_404(api: TestClient) -> None:
    response = borrow(api, MISSING_ID)

    assert response.status_code == 404
    assert response.json()["type"] == f"{TYPE}book-not-found"
    assert response.headers["content-type"] == PROBLEM


def test_unknown_loan_is_a_404(api: TestClient) -> None:
    response = api.get(f"/v1/loans/{MISSING_ID}")

    assert response.status_code == 404
    assert response.json()["type"] == f"{TYPE}loan-not-found"


def test_a_book_with_no_free_copy_is_a_409(api: TestClient) -> None:
    book_id = add_book(api, copies=1)
    borrow(api, book_id, "member-1")

    response = borrow(api, book_id, "member-2")

    assert response.status_code == 409
    assert response.json()["type"] == f"{TYPE}no-free-copy"


def test_the_same_member_and_book_twice_is_a_409(api: TestClient) -> None:
    book_id = add_book(api, copies=2)
    borrow(api, book_id, "member-1")

    response = borrow(api, book_id, "member-1")

    assert response.status_code == 409
    assert response.json()["type"] == f"{TYPE}already-borrowed"


def test_a_fourth_active_loan_is_a_409(api: TestClient) -> None:
    for number in range(1, 4):
        assert borrow(api, add_book(api, number)).status_code == 201
    fourth = add_book(api, 4)

    response = borrow(api, fourth)

    assert response.status_code == 409
    assert response.json()["type"] == f"{TYPE}member-limit-reached"


def test_rule_order_is_already_borrowed_then_limit_then_stock(api: TestClient) -> None:
    held = [add_book(api, n) for n in range(1, 4)]
    for book_id in held:
        borrow(api, book_id, "member-1")
    scarce = add_book(api, 4, copies=1)
    borrow(api, scarce, "member-2")  # the only copy is out

    holds_it_already = borrow(api, held[0], "member-1")  # also at the limit and no copy is free
    at_the_limit = borrow(api, scarce, "member-1")  # at the limit and no copy is free

    assert holds_it_already.json()["type"] == f"{TYPE}already-borrowed"
    assert at_the_limit.json()["type"] == f"{TYPE}member-limit-reached"


def test_return_defaults_to_today_and_frees_the_copy(api: TestClient) -> None:
    book_id = add_book(api)
    loan = borrow(api, book_id, "member-1").json()

    response = api.post(f"/v1/loans/{loan['id']}/return")

    assert response.status_code == 200
    assert response.json()["returned_on"] == "2026-01-06"
    assert borrow(api, book_id, "member-2").status_code == 201


def test_return_accepts_a_date(api: TestClient) -> None:
    loan = borrow(api, add_book(api)).json()

    response = api.post(f"/v1/loans/{loan['id']}/return", json={"returned_on": "2026-01-10"})

    assert response.json()["returned_on"] == "2026-01-10"


def test_returning_twice_is_a_409(api: TestClient) -> None:
    loan = borrow(api, add_book(api)).json()
    api.post(f"/v1/loans/{loan['id']}/return")

    response = api.post(f"/v1/loans/{loan['id']}/return")

    assert response.status_code == 409
    assert response.json()["type"] == f"{TYPE}loan-already-returned"


def test_returning_before_the_borrow_date_is_a_409_not_a_422(api: TestClient) -> None:
    loan = borrow(api, add_book(api)).json()

    response = api.post(f"/v1/loans/{loan['id']}/return", json={"returned_on": "2026-01-05"})

    assert response.status_code == 409
    assert response.json()["type"] == f"{TYPE}returned-before-borrowed"


def test_returning_an_unknown_loan_is_a_404(api: TestClient) -> None:
    assert api.post(f"/v1/loans/{MISSING_ID}/return").status_code == 404


def test_list_filters_by_member_and_activity(api: TestClient) -> None:
    first = borrow(api, add_book(api, 1), "member-1").json()
    second = borrow(api, add_book(api, 2), "member-1").json()
    borrow(api, add_book(api, 3), "member-2")
    api.post(f"/v1/loans/{second['id']}/return")

    mine = api.get("/v1/loans", params={"member_id": "member-1", "active": "true"}).json()
    returned = api.get("/v1/loans", params={"active": "false"}).json()
    paged = api.get("/v1/loans", params={"limit": 1, "offset": 1}).json()

    assert [loan["id"] for loan in mine["items"]] == [first["id"]]
    assert mine["total"] == 1
    assert [loan["id"] for loan in returned["items"]] == [second["id"]]
    assert (paged["total"], len(paged["items"]), paged["limit"], paged["offset"]) == (3, 1, 1, 1)


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/v1/loans", {"book_id": "nope", "member_id": "m"}),
        ("post", "/v1/loans", {"book_id": MISSING_ID, "member_id": ""}),
        ("post", "/v1/loans", {"book_id": MISSING_ID, "member_id": "has space"}),
        ("post", "/v1/loans", {"book_id": MISSING_ID}),
        ("post", "/v1/loans", {"book_id": MISSING_ID, "member_id": "m", "extra": True}),
        ("get", "/v1/loans/not-a-uuid", None),
        ("get", "/v1/loans?limit=0", None),
        ("get", "/v1/loans?active=maybe", None),
        ("post", f"/v1/loans/{MISSING_ID}/return", {"returned_on": 0}),
        ("post", f"/v1/loans/{MISSING_ID}/return", {"returned_on": "06/01/2026"}),
        ("post", f"/v1/loans/{MISSING_ID}/return", {"returned_on": "2026-01-06T10:00:00"}),
        ("post", "/v1/loans/not-a-uuid/return", None),
    ],
    ids=[
        "book-id-not-uuid",
        "empty-member",
        "member-with-space",
        "missing-member",
        "extra-field",
        "get-bad-uuid",
        "limit-zero",
        "active-not-bool",
        "return-date-as-number",
        "return-date-wrong-format",
        "return-date-is-datetime",
        "return-bad-uuid",
    ],
)
def test_invalid_input_is_a_422_problem(
    api: TestClient, method: str, path: str, payload: dict[str, Any] | None
) -> None:
    response = api.request(method, path, json=payload)

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["type"] == f"{TYPE}validation-error"
