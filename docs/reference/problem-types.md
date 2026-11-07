# Problem types

Every error body is `application/problem+json`. Branch on `type`; `title` is stable, `detail` is
for people. Types are `urn:problem:fastapi-szumplate:<slug>`.

| Slug | Status | Title | When |
| --- | --- | --- | --- |
| `validation-error` | 422 | Request validation failed | A body, path or query value is invalid on its own. `errors` lists `loc`, `msg`, `type`; the submitted value is never returned. |
| `service-not-ready` | 503 | Service not ready | A readiness check failed. `detail` names the checks, not the errors. |
| `book-not-found` | 404 | Book not found | The book id is unknown (also when lending). |
| `isbn-already-exists` | 409 | ISBN already exists | Another book has this ISBN. |
| `loan-not-found` | 404 | Loan not found | The loan id is unknown. |
| `already-borrowed` | 409 | Member already has this book | The member holds an active loan of this book. |
| `member-limit-reached` | 409 | Member loan limit reached | The member holds the maximum number of active loans. |
| `no-free-copy` | 409 | No free copy | Every copy of the book is on loan. |
| `loan-already-returned` | 409 | Loan already returned | The loan was returned before. |
| `returned-before-borrowed` | 409 | Returned before it was borrowed | `returned_on` is earlier than the borrow date. |

Lending checks its rules in this order: `already-borrowed`, `member-limit-reached`,
`no-free-copy`.

Errors the framework raises use `type` `about:blank` and the HTTP status phrase as `title`:

| Status | When |
| --- | --- |
| 400 | The body bytes are not decodable text (for example invalid UTF-8). |
| 404 | Unknown path. A trailing slash is not redirected; `/v1/books/` is a 404. |
| 405 | Wrong method; the `Allow` header lists every method of the path. |
| 500 | Unhandled error. Fixed text, no exception details. |

Every response carries an `X-Request-ID` header, a 500 included. The same value is in the body as
`request_id` and in every log line of the request.
