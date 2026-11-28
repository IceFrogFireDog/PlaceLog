"""관리자 API (/admin). 관리자 지정은 서버에서 `python -m app.tasks make-admin EMAIL`로만 한다."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_admin
from app.models import User
from app.routers._util import parse_uuid
from app.schemas.common import StrictModel
from app.services import admin_service
from app.services.pagination import clamp_limit, decode_offset, encode_offset

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminUserOut(BaseModel):
    id: str
    email: str
    username: str
    display_name: str
    created_at: datetime
    email_verified: bool
    two_factor_enabled: bool
    is_admin: bool
    suspended: bool
    photo_count: int


class AdminUserPage(BaseModel):
    items: list[AdminUserOut]
    next_cursor: str | None


class SuspendIn(StrictModel):
    suspended: bool


class DupPlaceOut(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    photo_count: int


class DupPairOut(BaseModel):
    a: DupPlaceOut
    b: DupPlaceOut
    distance_m: float


class MergeIn(StrictModel):
    source_id: str
    target_id: str


def _user(u: User, n: int) -> AdminUserOut:
    return AdminUserOut(
        id=str(u.id), email=u.email, username=u.username, display_name=u.display_name, created_at=u.created_at,
        email_verified=u.email_verified_at is not None, two_factor_enabled=u.two_factor_enabled, is_admin=u.is_admin,
        suspended=u.suspended_at is not None, photo_count=n,
    )


@router.get("/stats")
def stats(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return admin_service.stats(db)


@router.get("/users", response_model=AdminUserPage)
def users(q: str | None = Query(default=None, max_length=100), cursor: str | None = None, limit: int | None = None,
          admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    lim, off = clamp_limit(limit), decode_offset(cursor)
    rows = admin_service.list_users(db, q, off, lim + 1)
    return AdminUserPage(items=[_user(u, n) for u, n in rows[:lim]], next_cursor=encode_offset(off + lim) if len(rows) > lim else None)


@router.post("/users/{user_id}/suspend", response_model=AdminUserOut)
def suspend(user_id: str, data: SuspendIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = admin_service.set_suspended(db, admin, parse_uuid(user_id, "사용자"), data.suspended)
    return _user(u, 0)


@router.delete("/photos/{photo_id}", status_code=204)
def delete_photo(photo_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    admin_service.delete_photo(db, admin, parse_uuid(photo_id, "사진"))
    return Response(status_code=204)


@router.get("/places/duplicates", response_model=list[DupPairOut])
def duplicates(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    def out(p, n):
        return DupPlaceOut(id=str(p.id), name=p.name, latitude=p.latitude, longitude=p.longitude, photo_count=n)
    return [DupPairOut(a=out(a, na), b=out(b, nb), distance_m=round(d, 1)) for a, na, b, nb, d in admin_service.duplicate_places(db)]


@router.post("/places/merge")
def merge(data: MergeIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    moved = admin_service.merge_places(db, admin, parse_uuid(data.source_id, "장소"), parse_uuid(data.target_id, "장소"))
    return {"moved": moved}
