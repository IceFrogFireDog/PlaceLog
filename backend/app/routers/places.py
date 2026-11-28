from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import optional_user, require_verified_user
from app.models import Photo, Place, User
from app.routers._util import parse_uuid
from app.schemas.common import Page
from app.schemas.photo import PhotoListItem
from app.schemas.place import PlaceCreatedOut, PlaceCreateIn, PlaceDetailOut, PlaceOut
from app.services import photo_service, place_service
from app.services.pagination import clamp_limit, decode_offset, encode_offset, paginate_desc, split_page
from app.services.permission_service import visible_photo_query

router = APIRouter(prefix="/places", tags=["places"])


def _out(p: Place) -> PlaceOut:
    return PlaceOut(id=str(p.id), name=p.name, address=p.address, city=p.city, country_code=p.country_code, latitude=p.latitude, longitude=p.longitude, created_at=p.created_at)


@router.get("", response_model=Page[PlaceOut])
def search(q: str = Query(default="", max_length=100), cursor: str | None = None, limit: int | None = None, viewer: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    lim, off = clamp_limit(limit), decode_offset(cursor)
    rows = place_service.search(db, viewer, q, lim + 1, off)
    return Page(items=[_out(p) for p in rows[:lim]], next_cursor=encode_offset(off + lim) if len(rows) > lim else None)


@router.post("", status_code=201, response_model=PlaceCreatedOut)
def create(data: PlaceCreateIn, me: User = Depends(require_verified_user), db: Session = Depends(get_db)):
    place, cands = place_service.create(db, me, data)
    return PlaceCreatedOut(**_out(place).model_dump(), nearby_candidates=[_out(c) for c in cands])


@router.get("/{place_id}", response_model=PlaceDetailOut)
def detail(place_id: str, viewer: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    p = place_service.get(db, viewer, parse_uuid(place_id, "장소"))
    return PlaceDetailOut(**_out(p).model_dump(), photo_count=place_service.visible_photo_count(db, viewer, p.id))


@router.get("/{place_id}/photos", response_model=Page[PhotoListItem])
def photos(place_id: str, cursor: str | None = None, limit: int | None = None, viewer: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    p = place_service.get(db, viewer, parse_uuid(place_id, "장소"))
    lim = clamp_limit(limit)
    stmt = paginate_desc(photo_service.base_select().where(Photo.place_id == p.id, visible_photo_query(viewer)), Photo.created_at, Photo.id, cursor, lim)
    rows, nxt = split_page(photo_service.list_items(db, stmt), lim, key=lambda r: (r[0].created_at, r[0].id))
    return Page(items=[photo_service.to_list_item(*r) for r in rows], next_cursor=nxt)
