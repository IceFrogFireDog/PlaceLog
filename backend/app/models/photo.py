import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime, utcnow


class Visibility(str, enum.Enum):
    PUBLIC = "PUBLIC"
    FRIENDS = "FRIENDS"
    PRIVATE = "PRIVATE"


class PhotoStatus(str, enum.Enum):
    """업로드 직후에는 원본만 저장(PROCESSING)하고, 표시용·썸네일 변환이 끝나면 READY, 변환할 수 없으면 FAILED."""
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class Photo(Base):
    __tablename__ = "photos"
    __table_args__ = (
        CheckConstraint("visibility IN ('PUBLIC','FRIENDS','PRIVATE')", name="ck_photos_visibility"),
        CheckConstraint("status IN ('PROCESSING','READY','FAILED')", name="ck_photos_status"),
        CheckConstraint("shot_latitude IS NULL OR (shot_latitude >= -90 AND shot_latitude <= 90)", name="ck_photos_lat"),
        CheckConstraint("shot_longitude IS NULL OR (shot_longitude >= -180 AND shot_longitude <= 180)", name="ck_photos_lng"),
        Index("ix_photos_user_created", "user_id", "created_at"),
        Index("ix_photos_place_created", "place_id", "created_at"),
        # 지구본 전체 지도(WORLD)는 전체 공개·변환 완료 사진만 장소별로 센다 → 이 조건의 부분 인덱스로 인덱스만 읽고 집계
        Index("ix_photos_world_place", "place_id", postgresql_where=text("visibility = 'PUBLIC' AND status = 'READY'"),
              sqlite_where=text("visibility = 'PUBLIC' AND status = 'READY'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    # 장소 삭제 기능은 1차 범위 밖. 사진이 남은 장소는 삭제 불가(RESTRICT).
    place_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("places.id", ondelete="RESTRICT"))
    original_key: Mapped[str] = mapped_column(String(200))
    display_key: Mapped[str] = mapped_column(String(200))
    thumbnail_key: Mapped[str] = mapped_column(String(200))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    caption: Mapped[str] = mapped_column(Text, default="")
    visibility: Mapped[str] = mapped_column(String(10), default=Visibility.PRIVATE.value, index=True)
    taken_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    taken_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    shot_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    shot_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    share_exact_location: Mapped[bool] = mapped_column(Boolean, default=False)
    camera: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lens: Mapped[str | None] = mapped_column(String(120), nullable=True)
    focal_length: Mapped[float | None] = mapped_column(Float, nullable=True)
    aperture: Mapped[float | None] = mapped_column(Float, nullable=True)
    shutter_speed: Mapped[str | None] = mapped_column(String(20), nullable=True)
    iso: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 변환 작업 상태. 다른 사람에게는 READY인 사진만 보인다.
    status: Mapped[str] = mapped_column(String(10), default=PhotoStatus.READY.value, server_default=PhotoStatus.READY.value, index=True)
    processing_error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    processing_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
