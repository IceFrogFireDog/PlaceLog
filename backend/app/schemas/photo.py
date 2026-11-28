from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.database import taken_at_in_range
from app.schemas.common import StrictModel
from app.schemas.user import UserBrief

VisibilityLit = Literal["PUBLIC", "FRIENDS", "PRIVATE"]


class PhotoPlace(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float


class PhotoListItem(BaseModel):
    id: str
    owner: UserBrief
    place: PhotoPlace
    caption: str
    visibility: VisibilityLit
    width: int
    height: int
    thumbnail_url: str
    taken_at: datetime | None
    created_at: datetime


class PhotoDetail(PhotoListItem):
    display_url: str
    original_url: str | None  # 작성자에게만
    taken_timezone: str | None
    shot_latitude: float | None  # 권한 + share_exact_location 또는 본인
    shot_longitude: float | None
    share_exact_location: bool
    camera: str | None
    lens: str | None
    focal_length: float | None
    aperture: float | None
    shutter_speed: str | None
    iso: int | None
    is_owner: bool
    updated_at: datetime


class PhotoUpdateIn(StrictModel):
    caption: str | None = Field(default=None, max_length=2000)
    visibility: VisibilityLit | None = None
    place_id: str | None = None
    taken_at: datetime | None = None
    taken_timezone: str | None = Field(default=None, max_length=64)
    clear_taken_at: bool = False
    shot_latitude: float | None = Field(default=None, ge=-90, le=90)
    shot_longitude: float | None = Field(default=None, ge=-180, le=180)
    clear_shot_location: bool = False
    share_exact_location: bool | None = None

    @model_validator(mode="after")
    def _pair(self):
        if (self.shot_latitude is None) != (self.shot_longitude is None):
            raise ValueError("촬영 위도와 경도는 함께 입력해야 합니다.")
        if self.taken_at is not None and self.taken_at.tzinfo is None:
            raise ValueError("taken_at에는 시간대(오프셋)가 있어야 합니다.")
        if self.taken_at is not None and not taken_at_in_range(self.taken_at):
            raise ValueError("촬영일은 1826년~2099년 사이여야 합니다.")
        return self
