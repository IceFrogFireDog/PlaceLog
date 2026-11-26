"""운영 유지보수 작업 (python -m app.tasks …). 로컬 폴더와 S3 저장소 모두 지원."""
import uuid
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models import EmailToken, Photo, Place, User, UserSession
from app.services.place_service import DUPLICATE_RADIUS_M, haversine_m, normalize_name
from app.services.storage_service import age_seconds, get_storage


def _uuid(v: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(v)
    except ValueError:
        return None


def cleanup(db: Session, min_age_seconds: int = 3600) -> dict[str, int]:
    """DB에 없는 사진·프로필 사진 파일, 만료된 세션, 만료·사용된 메일 토큰을 지운다.
    업로드 중(파일 저장 후 DB 확정 전)인 파일을 지우지 않도록 min_age_seconds보다 오래된 파일만 대상.
    사용자 폴더 단위로 나눠 확인하므로 사진이 아주 많아도 메모리를 적게 쓴다."""
    storage = get_storage()
    photo_files = 0
    for owner in list(storage.list_children("photos/")):  # photos/<user>/<photo>/<file>
        uid = _uuid(owner)
        known = {str(i) for i in db.scalars(select(Photo.id).where(Photo.user_id == uid))} if uid else set()
        for key, mtime in list(storage.list_keys(f"photos/{owner}/")):
            parts = key.split("/")
            if len(parts) >= 4 and parts[2] not in known and age_seconds(mtime) > min_age_seconds:
                storage.delete(key)
                photo_files += 1

    avatar_files = 0
    for owner in list(storage.list_children("avatars/")):  # avatars/<user>/<file>
        uid = _uuid(owner)
        current = db.scalar(select(User.avatar_key).where(User.id == uid)) if uid else None
        for key, mtime in list(storage.list_keys(f"avatars/{owner}/")):
            if key != current and age_seconds(mtime) > min_age_seconds:
                storage.delete(key)
                avatar_files += 1

    now = utcnow()
    sessions = db.execute(delete(UserSession).where(UserSession.expires_at <= now)).rowcount
    tokens = db.execute(delete(EmailToken).where(or_(EmailToken.expires_at <= now, EmailToken.used_at <= now - timedelta(days=1)))).rowcount
    db.commit()
    return {"photo_files": photo_files, "avatar_files": avatar_files, "sessions": sessions or 0, "tokens": tokens or 0}


def find_duplicate_places(db: Session, radius_m: float = DUPLICATE_RADIUS_M) -> list[tuple[Place, Place, float]]:
    """같은 이름(정규화 기준)이고 radius_m 안에 있는 장소 쌍."""
    groups: dict[str, list[Place]] = defaultdict(list)
    for p in db.scalars(select(Place)):
        groups[normalize_name(p.name)].append(p)
    pairs = []
    for ps in groups.values():
        for i in range(len(ps)):
            for j in range(i + 1, len(ps)):
                d = haversine_m(ps[i].latitude, ps[i].longitude, ps[j].latitude, ps[j].longitude)
                if d <= radius_m:
                    pairs.append((ps[i], ps[j], d))
    return pairs


def merge_places(db: Session, source_id: uuid.UUID, target_id: uuid.UUID) -> int:
    """source 장소의 사진을 모두 target으로 옮기고 source를 지운다. 옮긴 사진 수를 반환."""
    if source_id == target_id:
        raise ValueError("같은 장소끼리는 합칠 수 없습니다.")
    source, target = db.get(Place, source_id), db.get(Place, target_id)
    if source is None or target is None:
        raise ValueError("장소를 찾을 수 없습니다.")
    moved = db.execute(update(Photo).where(Photo.place_id == source_id).values(place_id=target_id)).rowcount
    db.delete(source)
    db.commit()
    return moved or 0
