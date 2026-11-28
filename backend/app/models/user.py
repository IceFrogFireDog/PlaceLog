import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)  # 소문자 정규화 후 저장
    username: Mapped[str] = mapped_column(String(30), unique=True, index=True)  # 소문자 정규화 후 저장
    display_name: Mapped[str] = mapped_column(String(50))
    password_hash: Mapped[str] = mapped_column(String(255))
    bio: Mapped[str] = mapped_column(Text, default="")
    email_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    privacy_agreed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)  # 개인정보 안내 동의 시각
    avatar_key: Mapped[str | None] = mapped_column(String(200), nullable=True)  # 프로필 사진 저장 키
    # 2단계 인증(TOTP): 키 자체가 아니라 솔트만 저장 (app/core/totp.py)
    totp_salt: Mapped[str | None] = mapped_column(String(32), nullable=True)
    totp_pending_salt: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 설정 중(코드 확인 전)
    totp_enabled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # 같은 코드 재사용 방지
    # 운영: 관리자 여부(명령으로만 지정), 이용 정지 시각(정지되면 로그인 불가)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    suspended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def two_factor_enabled(self) -> bool:
        return self.totp_salt is not None


class RecoveryCode(Base):
    """2단계 인증 복구 코드 (인증 앱을 잃어버렸을 때 1회용). HMAC 해시만 저장."""
    __tablename__ = "recovery_codes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
