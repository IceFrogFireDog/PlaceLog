from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
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
    # 메일 링크(이메일 인증·비밀번호 재설정)에 쓰는 화면 주소
    frontend_base_url: str = "http://localhost:3000"

    # --- 저장소: local(비공개 폴더) 또는 object(S3 호환: AWS S3, Cloudflare R2, MinIO, NCP 등) ---
    storage_backend: Literal["local", "object"] = "local"
    local_storage_path: str = "./storage"
    object_storage_bucket: str = ""
    object_storage_endpoint_url: str = ""  # AWS S3면 비움
    object_storage_region: str = ""
    object_storage_access_key_id: str = ""
    object_storage_secret_access_key: str = ""
    object_storage_prefix: str = ""  # 버킷을 다른 용도와 나눠 쓸 때 앞에 붙는 경로

    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=200 * 1024 * 1024)
    # RAW(DNG·CR2·NEF·ARW 등) 파일 한도. 0이면 RAW 업로드를 받지 않는다.
    max_raw_upload_bytes: int = Field(default=80 * 1024 * 1024, ge=0, le=500 * 1024 * 1024)
    max_image_pixels: int = Field(default=80_000_000, ge=1_000_000, le=300_000_000)
    display_long_edge: int = 2400
    thumbnail_long_edge: int = 480
    avatar_size: int = 256
    image_workers: int = Field(default=2, ge=1, le=16)  # 동시 이미지 처리 수
    # 지구본 전체 지도(WORLD)의 전 지구 화면은 모두에게 같으므로 잠깐 캐시한다 (0이면 끔)
    map_cache_seconds: int = Field(default=15, ge=0, le=3600)

    # --- 이메일 인증·비밀번호 재설정 ---
    email_verification_required: bool = True  # 인증 전에는 사진 등록·장소 생성·친구 요청 불가
    verify_token_ttl_seconds: int = Field(default=24 * 3600, ge=300)
    reset_token_ttl_seconds: int = Field(default=3600, ge=300)
    mail_backend: Literal["file", "smtp", "none"] = "file"  # file: 개발용 메일함 폴더에 .eml로 저장
    mail_file_dir: str = "./dev-mail"
    mail_from: str = "지구본 사진 <no-reply@localhost>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    smtp_ssl: bool = False  # 465 포트(SSL) 사용 시 true

    # --- 장소 검색(지오코딩) 제공자 ---
    geocoder: Literal["nominatim", "kakao", "none"] = "nominatim"
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    geocoder_user_agent: str = "photo-globe/0.2"
    geocoder_contact_email: str = ""  # Nominatim 이용 정책상 연락처를 User-Agent에 넣는 것을 권장
    kakao_rest_api_key: str = ""
    geocode_cache_seconds: int = Field(default=24 * 3600, ge=0)

    # --- 빈도 제한: memory(단일 서버) 또는 redis(여러 서버 공유) ---
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    redis_url: str = "redis://localhost:6379/0"

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

    @field_validator("local_storage_path", "mail_file_dir")
    @classmethod
    def _relative_paths(cls, v: str) -> str:
        return _backend_relative(v)

    @field_validator("frontend_base_url")
    @classmethod
    def _frontend(cls, v: str) -> str:
        return v.strip().rstrip("/")

    @model_validator(mode="after")
    def _combos(self):
        if self.storage_backend == "object" and not self.object_storage_bucket:
            raise ValueError("STORAGE_BACKEND=object이면 OBJECT_STORAGE_BUCKET이 필요합니다.")
        if self.geocoder == "kakao" and not self.kakao_rest_api_key:
            raise ValueError("GEOCODER=kakao이면 KAKAO_REST_API_KEY가 필요합니다.")
        if self.mail_backend == "smtp" and not self.smtp_host:
            raise ValueError("MAIL_BACKEND=smtp이면 SMTP_HOST가 필요합니다.")
        return self

    @property
    def max_photo_request_bytes(self) -> int:
        """사진 업로드 요청 본문 한도 (일반 사진과 RAW 중 큰 쪽)."""
        return max(self.max_upload_bytes, self.max_raw_upload_bytes)

    @property
    def origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
