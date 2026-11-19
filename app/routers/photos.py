from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.database import get_db, taken_at_in_range
from app.core.errors import AppError
from app.dependencies.auth import optional_user, require_user
from app.models import User
from app.routers._util import parse_uuid
from app.schemas.photo import PhotoDetail, PhotoUpdateIn
from app.services import photo_service
from app.services.permission_service import get_visible_photo

router = APIRouter(prefix="/photos", tags=["photos"])


@router.post("", status_code=201, response_model=PhotoDetail)
async def create(
    file: UploadFile = File(...),
    place_id: str = Form(...),
    caption: str = Form(default="", max_length=2000),
    visibility: Literal["PUBLIC", "FRIENDS", "PRIVATE"] = Form(default="PRIVATE"),
    taken_at: datetime | None = Form(default=None),
    taken_timezone: str | None = Form(default=None, max_length=64),
    shot_latitude: float | None = Form(default=None, ge=-90, le=90),
    shot_longitude: float | None = Form(default=None, ge=-180, le=180),
    share_exact_location: bool = Form(default=False),
    use_exif_location: bool = Form(default=True),
    me: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if (shot_latitude is None) != (shot_longitude is None):
        raise AppError(422, "VALIDATION_ERROR", "촬영 좌표를 확인해 주세요.", {"shot_latitude": "위도·경도를 함께 입력해야 합니다."})
    if taken_at is not None and taken_at.tzinfo is None:
        raise AppError(422, "VALIDATION_ERROR", "촬영일을 확인해 주세요.", {"taken_at": "시간대(오프셋)가 필요합니다."})
    if taken_at is not None and not taken_at_in_range(taken_at):
        raise AppError(422, "VALIDATION_ERROR", "촬영일을 확인해 주세요.", {"taken_at": "1826년~2099년 사이여야 합니다."})
    for name, val in (("caption", caption), ("taken_timezone", taken_timezone)):
        if val is not None and "\x00" in val:
            raise AppError(422, "VALIDATION_ERROR", "입력값을 확인해 주세요.", {name: "허용되지 않는 문자가 있습니다."})
    try:
        pid = parse_uuid(place_id, "장소")
    except AppError as e:
        raise AppError(422, "VALIDATION_ERROR", "장소를 확인해 주세요.", {"place_id": "잘못된 ID"}) from e
    inp = photo_service.CreatePhotoInput(
        place_id=pid, caption=caption, visibility=visibility, taken_at=taken_at, taken_timezone=taken_timezone,
        shot_latitude=shot_latitude, shot_longitude=shot_longitude, share_exact_location=share_exact_location, use_exif_location=use_exif_location,
    )
    photo = await photo_service.create(db, me, file, inp)
    return await run_in_threadpool(photo_service.to_detail, db, me, photo)


@router.get("/{photo_id}", response_model=PhotoDetail)
def detail(photo_id: str, viewer: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    photo = get_visible_photo(db, viewer, parse_uuid(photo_id, "사진"))
    return photo_service.to_detail(db, viewer, photo)


@router.patch("/{photo_id}", response_model=PhotoDetail)
def update(photo_id: str, data: PhotoUpdateIn, me: User = Depends(require_user), db: Session = Depends(get_db)):
    photo = get_visible_photo(db, me, parse_uuid(photo_id, "사진"))
    photo_service.update(db, me, photo, data)
    return photo_service.to_detail(db, me, photo)


@router.delete("/{photo_id}", status_code=204)
def delete(photo_id: str, me: User = Depends(require_user), db: Session = Depends(get_db)):
    photo = get_visible_photo(db, me, parse_uuid(photo_id, "사진"))
    photo_service.delete(db, me, photo)
    return Response(status_code=204)
