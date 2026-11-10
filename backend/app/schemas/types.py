"""Reusable validated field types."""

from functools import lru_cache
from typing import Annotated
from zoneinfo import available_timezones

from pydantic import AfterValidator, StringConstraints


@lru_cache
def _valid_timezones() -> frozenset[str]:
    return frozenset(available_timezones() - {"Factory", "localtime"})


def _check_timezone(value: str) -> str:
    if value not in _valid_timezones():
        raise ValueError("must be an IANA time zone name, such as America/Toronto")
    return value


TimeZoneName = Annotated[str, AfterValidator(_check_timezone)]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
# The upper limit stops very long inputs from being used to make hashing expensive.
NewPassword = Annotated[str, StringConstraints(min_length=10, max_length=128)]
