"""사진 변환 작업 (원본 → 표시용·썸네일 WebP).

업로드 요청은 원본만 저장하고 PROCESSING 상태로 바로 응답한다. 변환은
1) 응답 직후 같은 서버의 백그라운드 작업이 바로 하고,
2) 서버가 그 사이 꺼졌거나 작업이 멈췄으면 작업자(python -m app.tasks worker)가 다시 처리한다.
같은 사진을 두 곳에서 동시에 처리하지 않도록 조건부 UPDATE로 작업을 '선점'한다.
"""
import logging
import uuid
from datetime import timedelta

import anyio
import anyio.to_thread
from sqlalchemy import and_, or_, select, update

from app.core.database import SessionLocal, utcnow
from app.core.errors import AppError
from app.models import Photo, PhotoStatus
from app.services import image_service
from app.services.storage_service import get_storage

log = logging.getLogger("app.processing")

STALE_SECONDS = 600  # 이 시간 넘게 끝나지 않은 작업은 멈춘 것으로 보고 다시 처리
UNCLAIMED_GRACE_SECONDS = 30  # 업로드 직후 백그라운드 작업이 시작할 시간을 준 뒤에 작업자가 가져간다
MAX_ATTEMPTS = 3
GENERIC_ERROR = "사진을 변환하지 못했습니다. 다시 시도하거나 다른 파일로 올려 주세요."


def _claim(db, pid: uuid.UUID) -> Photo | None:
    now = utcnow()
    res = db.execute(
        update(Photo)
        .where(
            Photo.id == pid,
            Photo.status == PhotoStatus.PROCESSING.value,
            or_(Photo.processing_started_at.is_(None), Photo.processing_started_at < now - timedelta(seconds=STALE_SECONDS)),
        )
        .values(processing_started_at=now, processing_attempts=Photo.processing_attempts + 1)
    )
    db.commit()
    if res.rowcount != 1:
        return None
    return db.get(Photo, pid)


def _finish(db, pid: uuid.UUID, status: PhotoStatus, error: str | None = None) -> bool:
    res = db.execute(
        update(Photo)
        .where(Photo.id == pid, Photo.status == PhotoStatus.PROCESSING.value)
        .values(status=status.value, processing_error=error, processing_started_at=None)
    )
    db.commit()
    return res.rowcount == 1


def process_photo(pid: uuid.UUID) -> str | None:
    """한 장 변환. 다른 곳에서 이미 처리 중이거나 끝났으면 아무것도 하지 않는다. 최종 상태를 반환."""
    storage = get_storage()
    with SessionLocal() as db:
        photo = _claim(db, pid)
        if photo is None:
            return None
        written: list[str] = []
        try:
            if photo.processing_attempts > MAX_ATTEMPTS:
                raise AppError(500, "PROCESSING_FAILED", "변환을 여러 번 시도했지만 실패했습니다. 다시 시도하거나 다른 파일로 올려 주세요.")
            processed = image_service.process(storage.read(photo.original_key))
            for key, blob in ((photo.display_key, processed.display), (photo.thumbnail_key, processed.thumbnail)):
                storage.save(key, blob)
                written.append(key)
        except AppError as e:  # 파일 자체 문제(손상·해상도) 또는 재시도 초과 → 다시 해도 같음
            log.info("photo %s processing failed: %s", pid, e.code)
            _cleanup(written)
            _finish(db, pid, PhotoStatus.FAILED, e.message[:200])
            return PhotoStatus.FAILED.value
        except Exception as e:  # noqa: BLE001 - 저장소 오류 등
            log.warning("photo %s processing error (%s)", pid, type(e).__name__)
            _cleanup(written)
            _finish(db, pid, PhotoStatus.FAILED, GENERIC_ERROR)
            return PhotoStatus.FAILED.value
        if not _finish(db, pid, PhotoStatus.READY):
            # 처리하는 동안 사진이 삭제되었으면 방금 만든 파일을 지운다 (세션 캐시가 아니라 DB에서 확인)
            if db.scalar(select(Photo.id).where(Photo.id == pid)) is None:
                _cleanup(written)
            return None
        return PhotoStatus.READY.value


def _cleanup(keys: list[str]) -> None:
    storage = get_storage()
    for k in keys:
        try:
            storage.delete(k)
        except Exception:  # noqa: BLE001 - 남은 파일은 정리 작업이 지운다
            log.warning("could not remove partial file")


async def run_job(pid: uuid.UUID) -> None:
    """응답 뒤 백그라운드에서 실행. 이미지 처리 동시 실행 수(IMAGE_WORKERS)를 지킨다."""
    from app.services.photo_service import image_limiter  # 순환 import 방지

    try:
        await anyio.to_thread.run_sync(process_photo, pid, limiter=image_limiter())
    except Exception:  # noqa: BLE001 - 남은 작업은 작업자가 다시 처리
        log.exception("background processing crashed for photo %s", pid)


def pending_ids(db, limit: int = 20) -> list[uuid.UUID]:
    """작업자가 가져갈 사진: 업로드 후 한동안 아무도 시작하지 않았거나, 시작했지만 멈춘 것."""
    now = utcnow()
    return list(db.scalars(
        select(Photo.id)
        .where(
            Photo.status == PhotoStatus.PROCESSING.value,
            or_(
                and_(Photo.processing_started_at.is_(None), Photo.created_at < now - timedelta(seconds=UNCLAIMED_GRACE_SECONDS)),
                Photo.processing_started_at < now - timedelta(seconds=STALE_SECONDS),
            ),
        )
        .order_by(Photo.created_at)
        .limit(limit)
    ))


def process_pending(limit: int = 20) -> dict[str, int]:
    """멈췄거나 시작되지 않은 변환 작업을 처리한다 (작업자·명령에서 호출)."""
    with SessionLocal() as db:
        ids = pending_ids(db, limit)
    result = {"READY": 0, "FAILED": 0, "skipped": 0}
    for pid in ids:
        status = process_photo(pid)
        result[status or "skipped"] += 1
    return result
