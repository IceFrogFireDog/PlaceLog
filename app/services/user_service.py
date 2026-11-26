"""사용자 표시 정보와 프로필 사진(아바타)."""
import logging
import secrets

import anyio
import anyio.to_thread
from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.models import User
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
