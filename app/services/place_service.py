import math
import re
import unicodedata
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, not_found
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


def normalize_name(name: str) -> str:
    """중복 판단용 이름: 전각/반각·대소문자·공백·문장부호 차이를 무시한다."""
    s = unicodedata.normalize("NFKC", name).casefold()
    return re.sub(r"[\s\W_]+", "", s)


def _out(p: Place) -> dict:
    return {
        "id": str(p.id), "name": p.name, "address": p.address, "city": p.city, "country_code": p.country_code,
        "latitude": p.latitude, "longitude": p.longitude, "created_at": p.created_at.isoformat(),
    }


def create(db: Session, user: User, data: PlaceCreateIn) -> tuple[Place, list[Place]]:
    """공유 장소 중복 정리 정책:
    - 같은 이름(정규화 기준)의 장소가 200m 안에 있으면 409 DUPLICATE_PLACE와 기존 장소를 돌려준다 → 기존 장소 사용을 권장.
    - 이름이 다르면 근처 후보만 안내하고 만든다.  - force=true면 확인 후 새로 만든다.
    - 조회자에게 보이지 않는 장소(남의 비공개 장소)는 비교 대상에서 빠진다 → 존재가 노출되지 않음.
    - 이미 생긴 중복은 관리 도구(`python -m app.tasks duplicates / merge-places`)로 합친다."""
    candidates = nearby(db, user, data.latitude, data.longitude)
    if not data.force:
        key = normalize_name(data.name)
        same = [c for c in candidates if normalize_name(c.name) == key]
        if same:
            raise AppError(
                409, "DUPLICATE_PLACE", f"근처에 같은 이름의 장소 ‘{same[0].name}’가 이미 있습니다. 기존 장소를 사용해 주세요.",
                extra={"existing_place": _out(same[0])},
            )
    place = Place(**data.model_dump(exclude={"force"}), created_by=user.id)
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
