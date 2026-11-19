from typing import Generic, TypeVar

from pydantic import BaseModel, model_validator

T = TypeVar("T")


def _has_nul(v) -> bool:
    if isinstance(v, str):
        return "\x00" in v
    if isinstance(v, dict):
        return any(_has_nul(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return any(_has_nul(x) for x in v)
    return False


class StrictModel(BaseModel):
    """입력용 스키마 기반: NUL 문자를 거부한다 (PostgreSQL text에 저장 불가 → 500 방지)."""

    @model_validator(mode="before")
    @classmethod
    def _reject_nul(cls, data):
        if _has_nul(data):
            raise ValueError("허용되지 않는 문자(NUL)가 포함되어 있습니다.")
        return data


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
