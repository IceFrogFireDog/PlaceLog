from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import not_found
from app.models import Friendship, FriendshipStatus, Photo, Place, User
from app.schemas.common import Page
from app.schemas.photo import PhotoListItem
from app.schemas.place import PlaceDetailOut
from app.schemas.user import AvatarOut, ProfileOut, ProfileUpdateIn, RelationOut, SearchUserOut, UserBrief
from app.dependencies.auth import optional_user, require_user
from app.services import friendship_service, photo_service, user_service
from app.services.user_view import avatar_url, brief
from app.services.pagination import clamp_limit, decode_offset, encode_offset, paginate_desc, split_page
from app.services.permission_service import visible_photo_query
from app.services.place_service import _escape_like

router = APIRouter(prefix="/users", tags=["users"])


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


@router.put("/me/avatar", response_model=AvatarOut)
async def upload_avatar(file: UploadFile = File(...), me: User = Depends(require_user), db: Session = Depends(get_db)):
    """프로필 사진 등록·교체. 가운데를 정사각형으로 잘라 저장하고 EXIF(위치정보)는 지운다."""
    user = await user_service.set_avatar(db, me, file)
    return AvatarOut(avatar_url=avatar_url(user))


@router.delete("/me/avatar", status_code=204)
def delete_avatar(me: User = Depends(require_user), db: Session = Depends(get_db)):
    user_service.remove_avatar(db, me)
    return Response(status_code=204)


@router.get("/{username}", response_model=ProfileOut)
def profile(username: str, viewer: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    u = _get_user(db, username)
    vis = visible_photo_query(viewer)
    photo_count = db.scalar(select(func.count(Photo.id)).where(Photo.user_id == u.id, vis)) or 0
    place_count = db.scalar(select(func.count(distinct(Photo.place_id))).where(Photo.user_id == u.id, vis)) or 0
    friend_count = None
    if viewer is not None and viewer.id == u.id:
        friend_count = db.scalar(
            select(func.count(Friendship.id)).where(or_(Friendship.user_low_id == u.id, Friendship.user_high_id == u.id), Friendship.status == FriendshipStatus.ACCEPTED.value)
        )
    return ProfileOut(
        **brief(u).model_dump(), bio=u.bio, created_at=u.created_at,
        photo_count=photo_count, place_count=place_count, friend_count=friend_count, relation=_relation(db, viewer, u),
    )


@router.get("/{username}/photos", response_model=Page[PhotoListItem])
def user_photos(username: str, cursor: str | None = None, limit: int | None = None, viewer: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    u = _get_user(db, username)
    lim = clamp_limit(limit)
    stmt = paginate_desc(photo_service.base_select().where(Photo.user_id == u.id, visible_photo_query(viewer)), Photo.created_at, Photo.id, cursor, lim)
    rows, nxt = split_page(photo_service.list_items(db, stmt), lim, key=lambda r: (r[0].created_at, r[0].id))
    return Page(items=[photo_service.to_list_item(*r) for r in rows], next_cursor=nxt)


@router.get("/{username}/places", response_model=Page[PlaceDetailOut])
def user_places(username: str, cursor: str | None = None, limit: int | None = None, viewer: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    u = _get_user(db, username)
    lim, off = clamp_limit(limit), decode_offset(cursor)
    cnt = func.count(Photo.id).label("cnt")
    rows = db.execute(
        select(Place, cnt).join(Photo, Photo.place_id == Place.id).where(Photo.user_id == u.id, visible_photo_query(viewer))
        .group_by(Place.id).order_by(cnt.desc(), Place.id).offset(off).limit(lim + 1)
    ).all()
    nxt = encode_offset(off + lim) if len(rows) > lim else None
    items = [
        PlaceDetailOut(id=str(p.id), name=p.name, address=p.address, city=p.city, country_code=p.country_code, latitude=p.latitude, longitude=p.longitude, created_at=p.created_at, photo_count=c)
        for p, c in rows[:lim]
    ]
    return Page(items=items, next_cursor=nxt)
