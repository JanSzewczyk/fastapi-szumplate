import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_szumplate.library.books.dependencies import get_book_repository
from fastapi_szumplate.library.books.repository import BookRepository, InMemoryBookRepository
from tests.library.factories import book_payload, isbn_for

PARALLEL = 8


class SlowIsbnCheckRepository(InMemoryBookRepository):
    """Widens the window between "is the ISBN free?" and the insert so a missing guard shows."""

    def _isbn_taken(self, isbn: str) -> bool:
        taken = super()._isbn_taken(isbn)
        time.sleep(0.01)
        return taken


@pytest.fixture
def slow_books(app: FastAPI) -> BookRepository:
    repository: BookRepository = SlowIsbnCheckRepository()
    app.dependency_overrides[get_book_repository] = lambda: repository
    return repository


@pytest.mark.concurrency
def test_only_one_of_eight_parallel_posts_with_the_same_isbn_is_created(
    app: FastAPI, slow_books: BookRepository
) -> None:
    barrier = threading.Barrier(PARALLEL, timeout=5)

    def post(_: int) -> int:
        client = TestClient(app)  # one client per thread
        barrier.wait()
        return client.post("/v1/books", json=book_payload(isbn=isbn_for(1))).status_code

    with ThreadPoolExecutor(PARALLEL) as pool:
        statuses = list(pool.map(post, range(PARALLEL)))

    assert sorted(statuses) == [201] + [409] * (PARALLEL - 1)
    assert slow_books.list_page(limit=100, offset=0)[1] == 1
