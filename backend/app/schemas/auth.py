import re

from app.schemas.common import StrictModel
from pydantic import BaseModel, EmailStr, Field, field_validator

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")
# /users/search, /users/me 같은 고정 경로·프론트 경로와 충돌하는 이름
RESERVED_USERNAMES = {
    "search", "me", "settings", "admin", "api", "login", "logout", "register", "upload", "friends", "places", "photos", "users",
    "new", "edit", "null", "undefined",
}


class RegisterIn(StrictModel):
    email: EmailStr
    username: str
    display_name: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        v = v.strip()
        if not USERNAME_RE.fullmatch(v):
            raise ValueError("닉네임은 영문·숫자·밑줄 3~30자입니다.")
        if v.lower() in RESERVED_USERNAMES:
            raise ValueError("사용할 수 없는 닉네임입니다.")
        return v.lower()

    @field_validator("display_name")
    @classmethod
    def _display(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("표시명을 입력해 주세요.")
        return v


class LoginIn(StrictModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class MeOut(BaseModel):
    id: str
    email: str
    username: str
    display_name: str
    bio: str
    csrf_token: str
