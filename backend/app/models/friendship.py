import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime, utcnow


class FriendshipStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"


class Friendship(Base):
    """두 사용자 쌍당 한 행. user_low_id < user_high_id로 정렬해 중복·역방향 중복을 DB에서 막는다."""

    __tablename__ = "friendships"
    __table_args__ = (
        UniqueConstraint("user_low_id", "user_high_id", name="uq_friendships_pair"),
        CheckConstraint("user_low_id < user_high_id", name="ck_friendships_order"),
        CheckConstraint("status IN ('PENDING','ACCEPTED')", name="ck_friendships_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_low_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    user_high_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    requester_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(10), default=FriendshipStatus.PENDING.value)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    def other(self, user_id: uuid.UUID) -> uuid.UUID:
        return self.user_high_id if self.user_low_id == user_id else self.user_low_id

    @property
    def addressee_id(self) -> uuid.UUID:
        return self.other(self.requester_id)
