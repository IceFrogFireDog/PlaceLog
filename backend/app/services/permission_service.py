"""공개범위 판단의 단일 출처. 사진·이미지·장소 통계·프로필·지구본이 모두 이 모듈을 사용한다."""
import uuid

from sqlalchemy import ColumnElement, and_, false, or_, select, union
from sqlalchemy.orm import Session

from app.core.errors import AppError, not_found
from app.models import Friendship, FriendshipStatus, Photo, PhotoStatus, Place, User, Visibility


def friend_ids_select(user_id: uuid.UUID):
    """수락된 친구 ID 서브쿼리."""
    acc = Friendship.status == FriendshipStatus.ACCEPTED.value
    return union(
        select(Friendship.user_high_id).where(Friendship.user_low_id == user_id, acc),
        select(Friendship.user_low_id).where(Friendship.user_high_id == user_id, acc),
    )


def _ready() -> ColumnElement[bool]:
    return Photo.status == PhotoStatus.READY.value


def visible_photo_query(viewer: User | None) -> ColumnElement[bool]:
    """조회자에게 보이는 사진 조건 (장소 기본 목록·프로필·상세에 사용).
    변환 중(PROCESSING)·실패(FAILED) 사진은 작성자에게만 보인다."""
    public = and_(_ready(), Photo.visibility == Visibility.PUBLIC.value)
    if viewer is None:
        return public
    return or_(
        Photo.user_id == viewer.id,
        public,
        and_(_ready(), Photo.visibility == Visibility.FRIENDS.value, Photo.user_id.in_(friend_ids_select(viewer.id))),
    )


def visible_place_filter(viewer: User | None) -> ColumnElement[bool]:
    """장소는 조회자에게 보이는 사진이 1장 이상 있거나 본인이 만든 경우에만 노출한다.
    (PRIVATE 사진만 있는 '우리집' 같은 장소의 이름·좌표가 검색으로 새지 않게)"""
    has_visible = select(Photo.id).where(Photo.place_id == Place.id, visible_photo_query(viewer)).exists()
    if viewer is None:
        return has_visible
    return or_(Place.created_by == viewer.id, has_visible)


def map_mode_filter(mode: str, viewer: User | None) -> ColumnElement[bool]:
    """지구본 필터: WORLD=전체 PUBLIC, FRIENDS=수락 친구의 PUBLIC·FRIENDS, ME=본인 전체. 모두 변환이 끝난(READY) 사진만."""
    if mode == "WORLD":
        return and_(_ready(), Photo.visibility == Visibility.PUBLIC.value)
    if viewer is None:
        raise AppError(401, "UNAUTHORIZED", "로그인이 필요합니다.")
    if mode == "FRIENDS":
        return and_(
            _ready(),
            Photo.user_id.in_(friend_ids_select(viewer.id)),
            Photo.visibility.in_([Visibility.PUBLIC.value, Visibility.FRIENDS.value]),
        )
    if mode == "ME":
        return and_(_ready(), Photo.user_id == viewer.id)
    return false()


def are_friends(db: Session, a: uuid.UUID, b: uuid.UUID) -> bool:
    low, high = sorted([a, b])
    f = db.scalar(select(Friendship).where(Friendship.user_low_id == low, Friendship.user_high_id == high))
    return f is not None and f.status == FriendshipStatus.ACCEPTED.value


def can_view_photo(db: Session, viewer: User | None, photo: Photo) -> bool:
    if viewer is not None and photo.user_id == viewer.id:
        return True
    if photo.status != PhotoStatus.READY.value:  # 변환 중·실패 사진은 작성자만
        return False
    if photo.visibility == Visibility.PUBLIC.value:
        return True
    if viewer is None:
        return False
    if photo.visibility == Visibility.FRIENDS.value:
        return are_friends(db, viewer.id, photo.user_id)
    return False


def get_visible_photo(db: Session, viewer: User | None, photo_id: uuid.UUID) -> Photo:
    """권한이 없으면 존재 여부도 숨기기 위해 404."""
    photo = db.get(Photo, photo_id)
    if photo is None or not can_view_photo(db, viewer, photo):
        raise not_found("사진")
    return photo


def require_owner(viewer: User, photo: Photo) -> None:
    if photo.user_id != viewer.id:
        raise AppError(403, "FORBIDDEN", "작성자만 할 수 있습니다.")


def can_download_original(viewer: User | None, photo: Photo) -> bool:
    """원본은 EXIF GPS가 남아 있으므로 1차에서는 작성자만 (지시서 11절)."""
    return viewer is not None and viewer.id == photo.user_id


def can_see_exact_location(viewer: User | None, photo: Photo) -> bool:
    """사진 조회 권한이 이미 확인된 상태에서 호출."""
    return (viewer is not None and viewer.id == photo.user_id) or photo.share_exact_location
