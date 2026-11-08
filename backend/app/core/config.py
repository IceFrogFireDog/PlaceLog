from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# backend/ 폴더. 실행 위치(cwd)와 무관하게 .env를 여기 기준으로 찾는다.
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str
    secret_key: str
    session_ttl_seconds: int = Field(default=14 * 24 * 3600, ge=300, le=90 * 24 * 3600)
    cookie_secure: bool = True
    allowed_origins: str = "http://localhost:3000"

    @field_validator("database_url")
    @classmethod
    def _db_url(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("DATABASE_URL is required")
        return v

    @field_validator("secret_key")
    @classmethod
    def _secret(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError('SECRET_KEY는 32자 이상 랜덤값이어야 합니다. 생성: python -c "import secrets; print(secrets.token_urlsafe(48))"')
        return v

    @property
    def origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
