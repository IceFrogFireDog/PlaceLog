"""관리자 기능: 통계, 사용자 정지, 사진 삭제, 중복 장소 합치기. 모든 조치는 로그에 ID만 남긴다."""
import logging
import uuid

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.core.errors import AppError, not_found
from app.models import Friendship, FriendshipStatus, Photo, PhotoStatus, Place, User, UserSession
from app.services import maintenance_service, photo_service

log = logging.getLogger("app.admin")


def stats(db: Session) -> dict:
    count = lambda stmt: db.scalar(stmt) or 0  # noqa: E731
    by_status = dict(db.execute(select(Photo.status, func.count()).group_by(Photo.status)).all())
    return {
        "users": count(select(func.count()).select_from(User)),
        "verified_users": count(select(func.count()).select_from(User).where(User.email_verified_at.is_not(None))),
        "suspended_users": count(select(func.count()).select_from(User).where(User.suspended_at.is_not(None))),
        "two_factor_users": count(select(func.count()).select_from(User).where(User.totp_salt.is_not(None))),
        "places": count(select(func.count()).select_from(Place)),
        "friendships": count(select(func.count()).select_from(Friendship).where(Friendship.status == FriendshipStatus.ACCEPTED.value)),
        "photos": {s.value: by_status.get(s.value, 0) for s in PhotoStatus},
    }


def list_users(db: Session, q: str | None, offset: int, limit: int) -> list[tuple[User, int]]:
    photo_count = select(func.count(Photo.id)).where(Photo.user_id == User.id).correlate(User).scalar_subquery()
    stmt = select(User, photo_count).order_by(User.created_at.desc()).offset(offset).limit(limit)
    if q and q.strip():
        pat = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(User.email.like(pat), User.username.like(pat), func.lower(User.display_name).like(pat)))
    return [(u, n) for u, n in db.execute(stmt).all()]


def set_suspended(db: Session, admin: User, target_id: uuid.UUID, suspended: bool) -> User:
    user = db.get(User, target_id)
    if user is None:
        raise not_found("사용자")
    if user.id == admin.id:
        raise AppError(422, "VALIDATION_ERROR", "자기 계정은 정지할 수 없습니다.")
    if user.is_admin and suspended:
        raise AppError(422, "VALIDATION_ERROR", "다른 관리자는 정지할 수 없습니다. 먼저 관리자 권한을 해제해 주세요.")
    user.suspended_at = utcnow() if suspended else None
    if suspended:
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))  # 즉시 로그아웃
    db.commit()
    log.info("admin %s %s user %s", admin.id, "suspended" if suspended else "restored", user.id)
    return user


def delete_photo(db: Session, admin: User, photo_id: uuid.UUID) -> None:
    """신고 처리 등으로 다른 사람의 사진을 지운다 (파일까지)."""
    photo = db.get(Photo, photo_id)
    if photo is None:
        raise not_found("사진")
    keys = [photo.original_key, photo.display_key, photo.thumbnail_key]
    owner = photo.user_id
    db.delete(photo)
    db.commit()
    photo_service._cleanup(keys)
    log.info("admin %s deleted photo %s of user %s", admin.id, photo_id, owner)


def duplicate_places(db: Session) -> list[tuple[Place, int, Place, int, float]]:
    pairs = maintenance_service.find_duplicate_places(db)
    ids = {p.id for a, b, _ in pairs for p in (a, b)}
    counts = dict(db.execute(select(Photo.place_id, func.count()).where(Photo.place_id.in_(ids)).group_by(Photo.place_id)).all()) if ids else {}
    return [(a, counts.get(a.id, 0), b, counts.get(b.id, 0), d) for a, b, d in pairs]


def merge_places(db: Session, admin: User, source: uuid.UUID, target: uuid.UUID) -> int:
    try:
        moved = maintenance_service.merge_places(db, source, target)
    except ValueError as e:
        raise AppError(422, "VALIDATION_ERROR", str(e)) from e
    log.info("admin %s merged place %s into %s (%d photos)", admin.id, source, target, moved)
    return moved
