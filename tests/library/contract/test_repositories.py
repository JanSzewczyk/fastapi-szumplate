"""Repository contract: a new adapter (SQL, say) passes it by subclassing and providing `repo`."""

from uuid import UUID

import pytest

from fastapi_szumplate.library.books.exceptions import BookNotFound, IsbnAlreadyExists
from fastapi_szumplate.library.books.repository import BookRepository, InMemoryBookRepository
from tests.library.factories import BookFactory, isbn_for


class BookRepositoryContract:
    """Behaviour every `BookRepository` adapter must have."""

    @pytest.fixture
    def repo(self) -> BookRepository:
        raise NotImplementedError

    def test_added_book_can_be_read_back(self, repo: BookRepository) -> None:
        book = BookFactory.build(title="Clean Code")

        repo.add(book)

        assert repo.get(book.id) == book

    def test_unknown_id_returns_none(self, repo: BookRepository) -> None:
        assert repo.get(UUID(int=7)) is None

    def test_second_book_with_the_same_isbn_is_refused(self, repo: BookRepository) -> None:
        repo.add(BookFactory.build(isbn=isbn_for(1)))

        with pytest.raises(IsbnAlreadyExists):
            repo.add(BookFactory.build(isbn=isbn_for(1)))

    def test_a_refused_book_is_not_stored(self, repo: BookRepository) -> None:
        repo.add(BookFactory.build(isbn=isbn_for(1)))
        refused = BookFactory.build(isbn=isbn_for(1))
        with pytest.raises(IsbnAlreadyExists):
            repo.add(refused)

        assert repo.get(refused.id) is None

    def test_update_replaces_the_stored_book(self, repo: BookRepository) -> None:
        book = BookFactory.build(title="Old")
        repo.add(book)
        changed = BookFactory.build(id=book.id, isbn=book.isbn, title="New")

        repo.update(changed)

        assert repo.get(book.id) == changed

    def test_update_of_an_unknown_book_is_refused(self, repo: BookRepository) -> None:
        with pytest.raises(BookNotFound):
            repo.update(BookFactory.build())

    def test_pages_keep_insertion_order_and_report_the_total(self, repo: BookRepository) -> None:
        books = BookFactory.build_batch(5)
        for book in books:
            repo.add(book)

        first, total = repo.list_page(limit=2, offset=0)
        last, _ = repo.list_page(limit=2, offset=4)
        beyond, _ = repo.list_page(limit=2, offset=10)

        assert first == books[:2]
        assert last == books[4:]
        assert beyond == []
        assert total == 5


class TestInMemoryBookRepository(BookRepositoryContract):
    @pytest.fixture
    def repo(self) -> BookRepository:
        return InMemoryBookRepository()
