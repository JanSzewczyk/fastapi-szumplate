"""Reusable annotated types that make the code match the spec's documented formats."""

import re
from datetime import date, datetime
from typing import Annotated, Any, Final

from pydantic import AwareDatetime, BeforeValidator

_ISO_DATE: Final = re.compile(r"\d{4}-\d{2}-\d{2}")


def _iso_date_only(value: Any) -> Any:
    """Accept a `date` or a `YYYY-MM-DD` string; reject the numbers Pydantic's lax mode reads."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and _ISO_DATE.fullmatch(value):
        return value
    raise ValueError("Input should be a date in ISO 8601 format, YYYY-MM-DD")


def _iso_aware_datetime_only(value: Any) -> Any:
    """Accept an aware `datetime` or an ISO 8601 string with `T` and an offset; reject numbers."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and "T" in value.upper():
        return value
    raise ValueError("Input should be a datetime in ISO 8601 format with a UTC offset")


type IsoDate = Annotated[date, BeforeValidator(_iso_date_only)]
type IsoAwareDatetime = Annotated[AwareDatetime, BeforeValidator(_iso_aware_datetime_only)]
