import math
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.models import Photo, Place, User
from app.schemas.place import PlaceCreateIn
from app.services.permission_service import visible_photo_query, visible_place_filter

DUPLICATE_RADIUS_M = 200


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search(db: Session, viewer: User | None, q: str, limit: int, offset: int = 0) -> list[Place]:
    q = q.strip()
    stmt = select(Place).where(visible_place_filter(viewer))
    if q:
        pat = f"%{_escape_like(q.lower())}%"
        stmt = stmt.where(or_(func.lower(Place.name).like(pat, escape="\\"), func.lower(Place.city).like(pat, escape="\\")))
    return list(db.scalars(stmt.order_by(Place.name, Place.id).offset(offset).limit(limit)))


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearby(db: Session, viewer: User | None, lat: float, lon: float, radius_m: float = DUPLICATE_RADIUS_M, exclude: uuid.UUID | None = None) -> list[Place]:
    dlat = radius_m / 111_000
    dlon = radius_m / max(1.0, 111_000 * math.cos(math.radians(lat)))
    cands = db.scalars(select(Place).where(Place.latitude.between(lat - dlat, lat + dlat), Place.longitude.between(lon - dlon, lon + dlon), visible_place_filter(viewer)).limit(50))
    return [p for p in cands if p.id != exclude and haversine_m(lat, lon, p.latitude, p.longitude) <= radius_m]


def create(db: Session, user: User, data: PlaceCreateIn) -> tuple[Place, list[Place]]:
    """새 장소를 만들고 200m 안의 기존 장소를 후보로 함께 돌려준다 (화면에서 기존 장소 사용을 권장).
    조회자에게 보이지 않는 장소(남의 비공개 장소)는 후보에서 빠진다 → 존재가 노출되지 않음."""
    candidates = nearby(db, user, data.latitude, data.longitude)
    place = Place(**data.model_dump(), created_by=user.id)
    db.add(place)
    db.commit()
    return place, candidates


def get(db: Session, viewer: User | None, place_id: uuid.UUID) -> Place:
    p = db.scalar(select(Place).where(Place.id == place_id, visible_place_filter(viewer)))
    if p is None:
        raise not_found("장소")
    return p


def visible_photo_count(db: Session, viewer: User | None, place_id: uuid.UUID) -> int:
    return db.scalar(select(func.count(Photo.id)).where(Photo.place_id == place_id, visible_photo_query(viewer))) or 0
