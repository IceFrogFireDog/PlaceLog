import re

from app.schemas.common import StrictModel
from pydantic import BaseModel, EmailStr, Field, field_validator

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")
# /users/search, /users/me 같은 고정 경로·프론트 경로와 충돌하는 이름
RESERVED_USERNAMES = {
    "search", "me", "settings", "admin", "api", "login", "logout", "register", "upload", "friends", "places", "photos", "users",
    "new", "edit", "null", "undefined", "privacy", "verify-email", "reset-password", "forgot-password",
}


class RegisterIn(StrictModel):
    email: EmailStr
    username: str
    display_name: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=12, max_length=128)
    # 개인정보 안내 동의 (필수). 빠져 있어도 아래 검사기가 한국어 메시지로 거절하도록 validate_default.
    agree_privacy: bool = Field(default=False, validate_default=True)

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

    @field_validator("agree_privacy")
    @classmethod
    def _agree(cls, v: bool) -> bool:
        if not v:
            raise ValueError("개인정보 안내에 동의해야 가입할 수 있습니다.")
        return v


class LoginIn(StrictModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)
    otp: str | None = Field(default=None, max_length=20)  # 2단계 인증 코드 또는 복구 코드


class PasswordIn(StrictModel):
    password: str = Field(min_length=1, max_length=128)


class OtpCodeIn(StrictModel):
    code: str = Field(min_length=1, max_length=20)


class PasswordOtpIn(StrictModel):
    password: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=20)


class TwoFactorSetupOut(BaseModel):
    secret: str  # 인증 앱에 직접 입력할 키 (QR을 못 찍을 때)
    otpauth_uri: str  # QR 코드 내용


class RecoveryCodesOut(BaseModel):
    recovery_codes: list[str]  # 한 번만 보여 준다


class TwoFactorStatusOut(BaseModel):
    enabled: bool
    recovery_codes_left: int


class TokenIn(StrictModel):
    token: str = Field(min_length=10, max_length=200)


class ForgotPasswordIn(StrictModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return v.strip().lower()


class ResetPasswordIn(StrictModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=12, max_length=128)


class ChangePasswordIn(StrictModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class MeOut(BaseModel):
    id: str
    email: str
    username: str
    display_name: str
    bio: str
    email_verified: bool
    avatar_url: str | None = None
    two_factor_enabled: bool = False
    is_admin: bool = False
    csrf_token: str


class MessageOut(BaseModel):
    message: str
