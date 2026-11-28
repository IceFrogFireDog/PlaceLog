from datetime import datetime

from app.schemas.common import StrictModel
from pydantic import BaseModel, Field, field_validator


class PlaceCreateIn(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    address: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=120)
    country_code: str | None = Field(default=None, pattern=r"^[A-Za-z]{2}$")
    force: bool = False  # 근처에 같은 이름의 장소가 있어도 새로 만들기

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("장소 이름을 입력해 주세요.")
        return v

    @field_validator("country_code")
    @classmethod
    def _cc(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class PlaceOut(BaseModel):
    id: str
    name: str
    address: str | None
    city: str | None
    country_code: str | None
    latitude: float
    longitude: float
    created_at: datetime


class PlaceDetailOut(PlaceOut):
    photo_count: int  # 조회자에게 허용된 사진 수


class PlaceCreatedOut(PlaceOut):
    nearby_candidates: list[PlaceOut] = []  # 중복 후보 안내
