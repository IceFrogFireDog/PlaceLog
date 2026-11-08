from datetime import datetime
from typing import Literal

from app.schemas.common import StrictModel
from pydantic import BaseModel, Field, field_validator

RelationStatus = Literal["SELF", "NONE", "OUTGOING", "INCOMING", "FRIENDS"]


class UserBrief(BaseModel):
    id: str
    username: str
    display_name: str


class RelationOut(BaseModel):
    status: RelationStatus
    friendship_id: str | None = None


class ProfileOut(UserBrief):
    bio: str
    created_at: datetime
    friend_count: int | None = None  # 본인에게만
    relation: RelationOut


class SearchUserOut(UserBrief):
    relation: RelationOut


class ProfileUpdateIn(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=50)
    bio: str | None = Field(default=None, max_length=500)

    @field_validator("display_name")
    @classmethod
    def _display(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("표시명을 입력해 주세요.")
        return v
