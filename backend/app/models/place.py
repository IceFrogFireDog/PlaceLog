import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime, utcnow


class Place(Base):
    __tablename__ = "places"
    __table_args__ = (
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_places_lat"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_places_lng"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), index=True)  # 이름만으로 유일 제약 두지 않음
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
