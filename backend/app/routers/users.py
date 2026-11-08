from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import not_found
from app.models import Friendship, FriendshipStatus, User
from app.schemas.common import Page
from app.schemas.user import ProfileOut, ProfileUpdateIn, RelationOut, SearchUserOut, UserBrief
from app.dependencies.auth import optional_user, require_user
from app.services import friendship_service
from app.services.user_view import brief
from app.services.pagination import clamp_limit, decode_offset, encode_offset

router = APIRouter(prefix="/users", tags=["users"])


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _relation(db: Session, viewer: User | None, target: User) -> RelationOut:
    status, f = friendship_service.relation(db, viewer, target.id)
    return RelationOut(status=status, friendship_id=str(f.id) if f else None)


def _get_user(db: Session, username: str) -> User:
    u = db.scalar(select(User).where(User.username == username.lower()))
    if u is None:
        raise not_found("사용자")
    return u


# 고정 경로를 동적 /{username}보다 먼저 등록
@router.get("/search", response_model=Page[SearchUserOut])
def search(q: str = Query(min_length=1, max_length=50), cursor: str | None = None, limit: int | None = None, me: User = Depends(require_user), db: Session = Depends(get_db)):
    pat = f"%{_escape_like(q.strip().lower())}%"
    lim, off = clamp_limit(limit), decode_offset(cursor)
    users = list(db.scalars(
        select(User).where(or_(User.username.like(pat, escape="\\"), func.lower(User.display_name).like(pat, escape="\\"))).order_by(User.username).offset(off).limit(lim + 1)
    ))
    items = [SearchUserOut(**brief(u).model_dump(), relation=_relation(db, me, u)) for u in users[:lim]]
    return Page(items=items, next_cursor=encode_offset(off + lim) if len(users) > lim else None)


@router.patch("/me", response_model=UserBrief)
def update_me(data: ProfileUpdateIn, me: User = Depends(require_user), db: Session = Depends(get_db)):
    if data.display_name is not None:
        me.display_name = data.display_name
    if data.bio is not None:
        me.bio = data.bio
    db.commit()
    return brief(me)


@router.get("/{username}", response_model=ProfileOut)
def profile(username: str, viewer: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    u = _get_user(db, username)
    friend_count = None
    if viewer is not None and viewer.id == u.id:
        friend_count = db.scalar(
            select(func.count(Friendship.id)).where(or_(Friendship.user_low_id == u.id, Friendship.user_high_id == u.id), Friendship.status == FriendshipStatus.ACCEPTED.value)
        )
    return ProfileOut(**brief(u).model_dump(), bio=u.bio, created_at=u.created_at, friend_count=friend_count, relation=_relation(db, viewer, u))
