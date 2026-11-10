"""Building blocks shared by the domain schemas."""

from typing import Annotated, Any

from pydantic import BaseModel, StringConstraints

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]
Minutes = Annotated[int, "Whole minutes; floats accumulate rounding error."]


class Page[T](BaseModel):
    items: list[T]
    total: int


def reject_null(value: Any) -> Any:
    """For PATCH fields that may be omitted but, unlike nullable columns, may not be cleared."""
    if value is None:
        raise ValueError("cannot be empty")
    return value
