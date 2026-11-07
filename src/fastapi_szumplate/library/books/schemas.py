"""Request and response schemas of the books API."""

from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from fastapi_szumplate.library.books.models import Book
from fastapi_szumplate.pagination import Page
from fastapi_szumplate.types import WholeNumber

Isbn = Annotated[
    str,
    Field(
        pattern=r"^[0-9]{13}$",  # not \d: Pydantic's regex engine reads \d as any Unicode digit
        description="ISBN-13, thirteen digits without hyphens. Unique across the catalogue.",
        examples=["9780132350884"],
    ),
]
Title = Annotated[
    str,
    Field(min_length=1, max_length=200, description="Title of the book.", examples=["Clean Code"]),
]
Author = Annotated[
    str,
    Field(
        min_length=1,
        max_length=200,
        description="Author of the book.",
        examples=["Robert C. Martin"],
    ),
]


class BookCreate(BaseModel):
    """Body of `POST /v1/books`."""

    model_config = ConfigDict(extra="forbid")

    isbn: Isbn
    title: Title
    author: Author
    copies: WholeNumber = Field(
        ge=1,
        le=1000,
        description="How many copies the library owns. Fixed once the book is created.",
        examples=[3],
    )


class BookUpdate(BaseModel):
    """Body of `PUT /v1/books/{book_id}`. The ISBN and the capacity cannot change."""

    model_config = ConfigDict(extra="forbid")

    title: Title
    author: Author


class BookResponse(BaseModel):
    """A book as the API shows it."""

    id: UUID = Field(
        description="Identifier assigned by the service.",
        examples=["0192f5e0-5a3b-7c11-9d2e-3f6a1b2c4d5e"],
    )
    isbn: Isbn
    title: Title
    author: Author
    copies: int = Field(description="How many copies the library owns.", examples=[3])

    @classmethod
    def from_domain(cls, book: Book) -> Self:
        """Build the response from the domain object."""
        return cls(
            id=book.id, isbn=book.isbn, title=book.title, author=book.author, copies=book.copies
        )


class BookPage(Page[BookResponse]):
    """One page of books."""
