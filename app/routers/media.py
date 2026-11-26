from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import not_found
from app.dependencies.auth import optional_user
from app.models import User
from app.routers._util import parse_uuid
from app.services.permission_service import can_download_original, get_visible_photo
from app.services.storage_service import get_storage

router = APIRouter(prefix="/media", tags=["media"])

NO_STORE = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
MIME = {"webp": "image/webp", "jpg": "image/jpeg", "png": "image/png", "heic": "image/heic"}
# 프로필 사진은 공개 프로필의 일부이고, 바꿀 때마다 주소가 달라지므로 오래 캐시해도 된다
AVATAR_CACHE = {"Cache-Control": "public, max-age=86400, immutable", "X-Content-Type-Options": "nosniff"}


def _serve(key: str, mime: str, headers: dict):
    storage = get_storage()
    path = storage.path_for(key)
    if path is not None:
        return FileResponse(path, media_type=mime, headers=headers)
    try:
        return Response(storage.read(key), media_type=mime, headers=headers)
    except FileNotFoundError as e:
        raise not_found("이미지") from e


@router.get("/avatars/{user_id}/{file_id}")
def avatar(user_id: str, file_id: str, db: Session = Depends(get_db)):
    user = db.get(User, parse_uuid(user_id, "사용자"))
    if user is None or not user.avatar_key or not user.avatar_key.endswith(f"/{file_id}.webp"):
        raise not_found("이미지")
    return _serve(user.avatar_key, "image/webp", AVATAR_CACHE)


@router.get("/{photo_id}/{variant}")
def media(photo_id: str, variant: Literal["thumbnail", "display", "original"], viewer: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    photo = get_visible_photo(db, viewer, parse_uuid(photo_id, "사진"))
    if variant == "original" and not can_download_original(viewer, photo):
        raise not_found("사진")  # 원본은 EXIF GPS 노출 방지를 위해 작성자만
    key = {"thumbnail": photo.thumbnail_key, "display": photo.display_key, "original": photo.original_key}[variant]
    mime = MIME.get(key.rsplit(".", 1)[-1], "application/octet-stream")
    return _serve(key, mime, NO_STORE)
