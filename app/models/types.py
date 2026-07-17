from enum import Enum
from typing import Any

from sqlalchemy import Enum as SAEnum


def enum_values(enum_class: type[Enum]) -> list[str]:
    """Persist string enum values instead of Python member names."""
    return [str(member.value) for member in enum_class]


def postgres_enum(enum_class: type[Enum], *, name: str) -> SAEnum[Any]:
    return SAEnum(enum_class, name=name, values_callable=enum_values)
