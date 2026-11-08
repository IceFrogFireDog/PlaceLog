from typing import Literal

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_user
from app.models import Friendship, FriendshipStatus, User
from app.routers._util import parse_uuid
from app.schemas.common import Page
from app.schemas.friendship import FriendRequestIn, FriendshipOut
from app.services.pagination import clamp_limit
from app.services import friendship_service
from app.services.user_view import brief

router = APIRouter(prefix="/friends", tags=["friends"])


def _out(db: Session, me: User, f: Friendship) -> FriendshipOut:
    other = db.get(User, f.other(me.id))
    direction = None
    if f.status == FriendshipStatus.PENDING.value:
        direction = "outgoing" if f.requester_id == me.id else "incoming"
    return FriendshipOut(
        id=str(f.id), status=f.status, direction=direction, created_at=f.created_at, accepted_at=f.accepted_at,
        user=brief(other),  # 이메일 미포함
    )


@router.post("/requests", status_code=201, response_model=FriendshipOut)
def send(data: FriendRequestIn, me: User = Depends(require_user), db: Session = Depends(get_db)):
    f = friendship_service.send_request(db, me, parse_uuid(data.target_user_id, "사용자"))
    return _out(db, me, f)


@router.get("", response_model=Page[FriendshipOut])
def friends(cursor: str | None = None, limit: int | None = None, me: User = Depends(require_user), db: Session = Depends(get_db)):
    rows, nxt = friendship_service.list_for(db, me, FriendshipStatus.ACCEPTED.value, cursor=cursor, limit=clamp_limit(limit))
    return Page(items=[_out(db, me, f) for f in rows], next_cursor=nxt)


@router.get("/requests", response_model=Page[FriendshipOut])
def requests(direction: Literal["incoming", "outgoing"] = "incoming", cursor: str | None = None, limit: int | None = None, me: User = Depends(require_user), db: Session = Depends(get_db)):
    rows, nxt = friendship_service.list_for(db, me, FriendshipStatus.PENDING.value, direction, cursor=cursor, limit=clamp_limit(limit))
    return Page(items=[_out(db, me, f) for f in rows], next_cursor=nxt)


@router.post("/{friendship_id}/accept", response_model=FriendshipOut)
def accept(friendship_id: str, me: User = Depends(require_user), db: Session = Depends(get_db)):
    return _out(db, me, friendship_service.accept(db, me, parse_uuid(friendship_id, "친구 관계")))


@router.post("/{friendship_id}/reject", status_code=204)
def reject(friendship_id: str, me: User = Depends(require_user), db: Session = Depends(get_db)):
    friendship_service.reject(db, me, parse_uuid(friendship_id, "친구 관계"))
    return Response(status_code=204)


@router.delete("/{friendship_id}", status_code=204)
def remove(friendship_id: str, me: User = Depends(require_user), db: Session = Depends(get_db)):
    friendship_service.remove(db, me, parse_uuid(friendship_id, "친구 관계"))
    return Response(status_code=204)
