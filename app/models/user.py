import uuid
from datetime import datetime

from sqlalchemy import String, Text, Uuid
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
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None
