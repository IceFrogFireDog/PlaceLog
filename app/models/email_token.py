import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime, utcnow


class TokenPurpose(str, enum.Enum):
    VERIFY = "VERIFY"  # 이메일 인증
    RESET = "RESET"  # 비밀번호 재설정


class EmailToken(Base):
    """메일 링크용 1회성 토큰. 원문은 메일에만 있고 DB에는 SHA-256 해시만 저장한다."""

    __tablename__ = "email_tokens"
    __table_args__ = (CheckConstraint("purpose IN ('VERIFY','RESET')", name="ck_email_tokens_purpose"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(10))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
