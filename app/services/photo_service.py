import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

import anyio
import anyio.to_thread
from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.models import Photo, Place, User
from app.schemas.photo import PhotoDetail, PhotoListItem, PhotoPlace, PhotoUpdateIn
from app.services import exif_service, image_service
from app.services.permission_service import can_download_original, can_see_exact_location, require_owner, visible_place_filter
from app.services.storage_service import get_storage
from app.services.user_view import brief

log = logging.getLogger("app.photos")


@dataclass
class CreatePhotoInput:
    place_id: uuid.UUID
    caption: str
    visibility: str
    taken_at: datetime | None
    taken_timezone: str | None
    shot_latitude: float | None
    shot_longitude: float | None
    share_exact_location: bool
    use_exif_location: bool
    use_exif_date: bool = True


def _too_large(limit: int) -> AppError:
    return AppError(413, "FILE_TOO_LARGE", f"파일은 {limit // (1024 * 1024)}MB 이하만 올릴 수 있습니다.")


async def read_upload_limited(file: UploadFile, limit: int | None = None) -> bytes:
    limit = limit or settings.max_upload_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise _too_large(limit)
    if not data:
        raise AppError(422, "EMPTY_FILE", "파일이 비어 있습니다.", {"file": "파일을 선택해 주세요."})
    return data


def _create_sync(db: Session, user: User, data: bytes, inp: CreatePhotoInput) -> Photo:
    """형식 검사 → EXIF 추출 → 표시용·썸네일 변환 → 원본과 함께 저장 → DB 등록. 중간에 실패하면 저장한 파일을 지운다."""
    if db.scalar(select(Place.id).where(Place.id == inp.place_id, visible_place_filter(user))) is None:
        raise AppError(422, "VALIDATION_ERROR", "장소를 확인해 주세요.", {"place_id": "존재하지 않는 장소입니다."})
    processed = image_service.process(data)  # 실제 형식·해상도 검사 실패 시 415/413
    exif = exif_service.extract(data)

    shot_lat, shot_lon = inp.shot_latitude, inp.shot_longitude
    if shot_lat is None and inp.use_exif_location:
        shot_lat, shot_lon = exif.latitude, exif.longitude
    taken_at, taken_tz = inp.taken_at, inp.taken_timezone
    if taken_at is None and inp.use_exif_date and exif.taken_at is not None:  # 시간대가 있는 EXIF만 자동 사용
        taken_at, taken_tz = exif.taken_at, exif.taken_timezone

    pid = uuid.uuid4()
    base = f"photos/{user.id}/{pid}"
    keys = {"original": f"{base}/original.{processed.original_ext}", "display": f"{base}/display.webp", "thumbnail": f"{base}/thumb.webp"}
    storage = get_storage()
    try:
        storage.save(keys["original"], data)
        storage.save(keys["display"], processed.display)
        storage.save(keys["thumbnail"], processed.thumbnail)
    except Exception as e:
        _cleanup(list(keys.values()))
        log.error("storage save failed for photo %s", pid)
        raise AppError(500, "STORAGE_ERROR", "사진 저장에 실패했습니다. 다시 시도해 주세요.") from e

    photo = Photo(
        id=pid, user_id=user.id, place_id=inp.place_id,
        original_key=keys["original"], display_key=keys["display"], thumbnail_key=keys["thumbnail"],
        width=processed.width, height=processed.height,
        caption=inp.caption, visibility=inp.visibility,
        taken_at=taken_at, taken_timezone=taken_tz,
        shot_latitude=shot_lat, shot_longitude=shot_lon, share_exact_location=inp.share_exact_location,
        camera=exif.camera, lens=exif.lens, focal_length=exif.focal_length, aperture=exif.aperture,
        shutter_speed=exif.shutter_speed, iso=exif.iso,
    )
    db.add(photo)
    try:
        db.commit()
    except Exception:
        db.rollback()
        _cleanup(list(keys.values()))
        raise
    return photo


_image_limiter: anyio.CapacityLimiter | None = None


def image_limiter() -> anyio.CapacityLimiter:
    """사진 등록·프로필 사진 처리가 함께 쓰는 동시 처리 한도 (IMAGE_WORKERS). 큰 사진을 한꺼번에 여러 장 풀어 메모리가 넘치지 않게 한다."""
    global _image_limiter
    if _image_limiter is None:  # 이벤트 루프 안에서 처음 쓸 때 생성
        _image_limiter = anyio.CapacityLimiter(settings.image_workers)
    return _image_limiter


async def create(db: Session, user: User, file: UploadFile, inp: CreatePhotoInput) -> Photo:
    data = await read_upload_limited(file)
    # 순서를 기다리는 동안 DB 커넥션을 붙잡지 않도록 인증 조회 트랜잭션을 끝낸다 (expire_on_commit=False라 user 값 유지)
    await run_in_threadpool(db.commit)
    # 대기는 이벤트 루프에서 하므로 공용 스레드풀(다른 API 요청)을 막지 않는다
    return await anyio.to_thread.run_sync(_create_sync, db, user, data, inp, limiter=image_limiter())


def _cleanup(keys: list[str]) -> list[str]:
    failed = []
    storage = get_storage()
    for k in keys:
        try:
            storage.delete(k)
        except Exception:  # noqa: BLE001
            failed.append(k)
    if failed:
        log.warning("file cleanup failed (%d files); `python -m app.tasks cleanup` will retry", len(failed))
    return failed


def update(db: Session, user: User, photo: Photo, data: PhotoUpdateIn) -> Photo:
    require_owner(user, photo)
    if data.caption is not None:
        photo.caption = data.caption
    if data.visibility is not None:
        photo.visibility = data.visibility
    if data.place_id is not None:
        try:
            new_place = uuid.UUID(data.place_id)
        except ValueError as e:
            raise AppError(422, "VALIDATION_ERROR", "장소를 확인해 주세요.", {"place_id": "잘못된 ID"}) from e
        if db.scalar(select(Place.id).where(Place.id == new_place, visible_place_filter(user))) is None:
            raise AppError(422, "VALIDATION_ERROR", "장소를 확인해 주세요.", {"place_id": "존재하지 않는 장소입니다."})
        photo.place_id = new_place
    if data.clear_taken_at:
        photo.taken_at, photo.taken_timezone = None, None
    elif data.taken_at is not None:
        photo.taken_at, photo.taken_timezone = data.taken_at, data.taken_timezone
    if data.clear_shot_location:
        photo.shot_latitude, photo.shot_longitude = None, None
    elif data.shot_latitude is not None:
        photo.shot_latitude, photo.shot_longitude = data.shot_latitude, data.shot_longitude
    if data.share_exact_location is not None:
        photo.share_exact_location = data.share_exact_location
    db.commit()
    return photo


def delete(db: Session, user: User, photo: Photo) -> None:
    require_owner(user, photo)
    keys = [photo.original_key, photo.display_key, photo.thumbnail_key]
    db.delete(photo)
    db.commit()  # DB 먼저 확정 → 파일 정리 실패분은 정리 작업(python -m app.tasks cleanup)이 다시 지운다
    _cleanup(keys)


# ---------- 직렬화 ----------

def media_url(photo_id: uuid.UUID, variant: str) -> str:
    return f"/api/v1/media/{photo_id}/{variant}"


def _place(p: Place) -> PhotoPlace:
    return PhotoPlace(id=str(p.id), name=p.name, latitude=p.latitude, longitude=p.longitude)


def to_list_item(photo: Photo, owner: User, place: Place) -> PhotoListItem:
    return PhotoListItem(
        id=str(photo.id), owner=brief(owner), place=_place(place), caption=photo.caption, visibility=photo.visibility,
        width=photo.width, height=photo.height, thumbnail_url=media_url(photo.id, "thumbnail"),
        taken_at=photo.taken_at, created_at=photo.created_at,
    )


def to_detail(db: Session, viewer: User | None, photo: Photo) -> PhotoDetail:
    owner, place = db.get(User, photo.user_id), db.get(Place, photo.place_id)
    is_owner = viewer is not None and viewer.id == photo.user_id
    exact = can_see_exact_location(viewer, photo)
    base = to_list_item(photo, owner, place).model_dump()
    return PhotoDetail(
        **base,
        display_url=media_url(photo.id, "display"),
        original_url=media_url(photo.id, "original") if can_download_original(viewer, photo) else None,
        taken_timezone=photo.taken_timezone,
        shot_latitude=photo.shot_latitude if exact else None,
        shot_longitude=photo.shot_longitude if exact else None,
        share_exact_location=photo.share_exact_location,
        camera=photo.camera, lens=photo.lens, focal_length=photo.focal_length, aperture=photo.aperture,
        shutter_speed=photo.shutter_speed, iso=photo.iso, is_owner=is_owner, updated_at=photo.updated_at,
    )


def list_items(db: Session, stmt) -> list[tuple[Photo, User, Place]]:
    """stmt는 select(Photo, User, Place).join(...) 형태."""
    return [tuple(r) for r in db.execute(stmt).all()]


def base_select():
    return select(Photo, User, Place).join(User, User.id == Photo.user_id).join(Place, Place.id == Photo.place_id)
