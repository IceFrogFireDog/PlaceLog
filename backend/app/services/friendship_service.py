import uuid

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.core.errors import AppError, not_found
from app.models import Friendship, FriendshipStatus, User
from app.services.pagination import paginate_desc, split_page


def _pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    low, high = sorted([a, b])
    return low, high


def get_between(db: Session, a: uuid.UUID, b: uuid.UUID) -> Friendship | None:
    low, high = _pair(a, b)
    return db.scalar(select(Friendship).where(Friendship.user_low_id == low, Friendship.user_high_id == high))


def relation(db: Session, viewer: User | None, target_id: uuid.UUID) -> tuple[str, Friendship | None]:
    if viewer is None:
        return "NONE", None
    if viewer.id == target_id:
        return "SELF", None
    f = get_between(db, viewer.id, target_id)
    if f is None:
        return "NONE", None
    if f.status == FriendshipStatus.ACCEPTED.value:
        return "FRIENDS", f
    return ("OUTGOING" if f.requester_id == viewer.id else "INCOMING"), f


def send_request(db: Session, me: User, target_id: uuid.UUID) -> Friendship:
    if target_id == me.id:
        raise AppError(422, "SELF_REQUEST", "자기 자신에게 친구 요청을 보낼 수 없습니다.")
    if db.get(User, target_id) is None:
        raise not_found("사용자")
    existing = get_between(db, me.id, target_id)
    if existing is not None:
        if existing.status == FriendshipStatus.ACCEPTED.value:
            raise AppError(409, "ALREADY_FRIENDS", "이미 친구입니다.")
        if existing.requester_id == me.id:
            raise AppError(409, "ALREADY_REQUESTED", "이미 요청을 보냈습니다.")
        # 반대 방향 요청은 자동 수락하지 않는다.
        raise AppError(409, "INCOMING_REQUEST_EXISTS", "상대가 보낸 요청이 있습니다. 받은 요청에서 수락해 주세요.")
    low, high = _pair(me.id, target_id)
    f = Friendship(user_low_id=low, user_high_id=high, requester_id=me.id, status=FriendshipStatus.PENDING.value)
    db.add(f)
    try:
        db.commit()
    except IntegrityError as e:  # 동시 요청
        db.rollback()
        raise AppError(409, "ALREADY_REQUESTED", "이미 요청이 존재합니다.") from e
    return f


def _get_involving(db: Session, me: User, friendship_id: uuid.UUID) -> Friendship:
    f = db.get(Friendship, friendship_id)
    if f is None or me.id not in (f.user_low_id, f.user_high_id):
        raise not_found("친구 관계")  # 제삼자에게는 존재도 숨김
    return f


def accept(db: Session, me: User, friendship_id: uuid.UUID) -> Friendship:
    f = _get_involving(db, me, friendship_id)
    if f.status != FriendshipStatus.PENDING.value or f.requester_id == me.id:
        raise AppError(403, "FORBIDDEN", "받은 대기 중 요청만 수락할 수 있습니다.")
    f.status = FriendshipStatus.ACCEPTED.value
    f.accepted_at = utcnow()
    db.commit()
    return f


def reject(db: Session, me: User, friendship_id: uuid.UUID) -> None:
    f = _get_involving(db, me, friendship_id)
    if f.status != FriendshipStatus.PENDING.value or f.requester_id == me.id:
        raise AppError(403, "FORBIDDEN", "받은 대기 중 요청만 거절할 수 있습니다.")
    db.delete(f)
    db.commit()


def remove(db: Session, me: User, friendship_id: uuid.UUID) -> None:
    """보낸 요청 취소 또는 친구 해제. 받은 요청은 reject를 사용."""
    f = _get_involving(db, me, friendship_id)
    if f.status == FriendshipStatus.PENDING.value and f.requester_id != me.id:
        raise AppError(403, "FORBIDDEN", "받은 요청은 거절을 사용해 주세요.")
    db.delete(f)
    db.commit()


def list_for(db: Session, me: User, status: str, direction: str | None = None, cursor: str | None = None, limit: int = 24) -> tuple[list[Friendship], str | None]:
    stmt = select(Friendship).where(or_(Friendship.user_low_id == me.id, Friendship.user_high_id == me.id), Friendship.status == status)
    if direction == "outgoing":
        stmt = stmt.where(Friendship.requester_id == me.id)
    elif direction == "incoming":
        stmt = stmt.where(Friendship.requester_id != me.id)
    rows = list(db.scalars(paginate_desc(stmt, Friendship.created_at, Friendship.id, cursor, limit)))
    return split_page(rows, limit)
