from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# backend/ 폴더. 실행 위치(cwd)와 무관하게 .env와 상대 경로 저장소를 여기 기준으로 찾는다.
BACKEND_DIR = Path(__file__).resolve().parents[2]


def _backend_relative(v: str) -> str:
    p = Path(v).expanduser()
    return str(p if p.is_absolute() else (BACKEND_DIR / p).resolve())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str
    secret_key: str
    session_ttl_seconds: int = Field(default=14 * 24 * 3600, ge=300, le=90 * 24 * 3600)
    cookie_secure: bool = True
    allowed_origins: str = "http://localhost:3000"

    # --- 저장소: 비공개 로컬 폴더 ---
    local_storage_path: str = "./storage"

    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=200 * 1024 * 1024)
    max_image_pixels: int = Field(default=80_000_000, ge=1_000_000, le=300_000_000)
    display_long_edge: int = 2400
    thumbnail_long_edge: int = 480
    image_workers: int = Field(default=2, ge=1, le=16)  # 동시 이미지 처리 수

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

    @field_validator("local_storage_path")
    @classmethod
    def _relative_paths(cls, v: str) -> str:
        return _backend_relative(v)

    @property
    def origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
