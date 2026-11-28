"""사용자 표시 정보와 프로필 사진(아바타)."""
import logging
import secrets

import anyio
import anyio.to_thread
from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, exists, or_, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import verify_password
from app.models import EmailToken, Friendship, Photo, Place, RecoveryCode, User, UserSession
from app.services import image_service
from app.services.photo_service import image_limiter, read_upload_limited
from app.services.storage_service import get_storage
from app.services.user_view import avatar_url, brief  # noqa: F401 - 다른 모듈에서 user_service.brief로 사용

log = logging.getLogger("app.users")


def _delete_quietly(key: str | None) -> None:
    if not key:
        return
    try:
        get_storage().delete(key)
    except Exception:  # noqa: BLE001 - 남은 파일은 정리 작업(cleanup)이 지운다
        log.warning("old avatar cleanup failed; will be removed by cleanup task")


def _save_avatar_sync(db: Session, user: User, data: bytes) -> User:
    webp = image_service.make_avatar(data)
    key = f"avatars/{user.id}/{secrets.token_hex(8)}.webp"
    get_storage().save(key, webp)
    old = user.avatar_key
    user.avatar_key = key
    try:
        db.commit()
    except Exception:
        db.rollback()
        _delete_quietly(key)
        raise
    _delete_quietly(old)
    return user


async def set_avatar(db: Session, user: User, file: UploadFile) -> User:
    data = await read_upload_limited(file)
    await run_in_threadpool(db.commit)  # 처리 대기 중 DB 커넥션을 붙잡지 않게
    return await anyio.to_thread.run_sync(_save_avatar_sync, db, user, data, limiter=image_limiter())


def remove_avatar(db: Session, user: User) -> None:
    old = user.avatar_key
    user.avatar_key = None
    db.commit()
    _delete_quietly(old)


def delete_account(db: Session, user: User, password: str) -> int:
    """계정과 그 사용자의 사진·파일·친구 관계·로그인·메일 토큰을 지운다. 지운 사진 수를 반환.
    - 이 사용자가 만든 장소: 남은 사진이 없으면 삭제, 다른 사람 사진이 있으면 공유 장소로 남기고 만든 사람 정보만 지운다.
    - DB를 먼저 확정하고 파일을 지운다. 파일 삭제가 실패해도 정리 작업(python -m app.tasks cleanup)이 다시 지운다."""
    if not verify_password(password, user.password_hash):
        raise AppError(422, "INVALID_PASSWORD", "비밀번호가 올바르지 않습니다.", {"password": "비밀번호가 올바르지 않습니다."})
    uid = user.id
    rows = db.execute(select(Photo.original_key, Photo.display_key, Photo.thumbnail_key).where(Photo.user_id == uid)).all()
    keys = [k for row in rows for k in row if k]
    if user.avatar_key:
        keys.append(user.avatar_key)
    # SQLite는 외래키 연쇄 삭제를 강제하지 않으므로 직접 지운다
    db.execute(delete(Photo).where(Photo.user_id == uid))
    db.execute(delete(Friendship).where(or_(Friendship.user_low_id == uid, Friendship.user_high_id == uid, Friendship.requester_id == uid)))
    db.execute(delete(UserSession).where(UserSession.user_id == uid))
    db.execute(delete(EmailToken).where(EmailToken.user_id == uid))
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == uid))
    db.execute(delete(Place).where(Place.created_by == uid, ~exists().where(Photo.place_id == Place.id)))
    db.execute(update(Place).where(Place.created_by == uid).values(created_by=None))
    db.delete(user)
    db.commit()
    for key in keys:
        _delete_quietly(key)
    return len(rows)
