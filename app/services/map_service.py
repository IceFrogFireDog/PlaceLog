"""지구본 핀·클러스터. 권한 필터를 통과한 사진만 집계한다.

낮은 확대(zoom < PLACE_ZOOM)에서는 클러스터 계산까지 DB에서 한다(격자 칸별 GROUP BY).
장소를 모두 가져와 파이썬에서 묶지 않으므로 장소가 많아도 응답 크기와 메모리가 일정하다.
"""
import uuid

from sqlalchemy import Integer, String, and_, cast, func, or_, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.sql.functions import FunctionElement

from app.core.errors import AppError
from app.models import Photo, Place, User
from app.schemas.map import MapCluster, MapPlace, MapResponse
from app.services.permission_service import map_mode_filter

MAX_ZOOM = 20
PLACE_ZOOM = 6  # 이 이상이면 개별 장소 핀
MAX_ITEMS = 500


def parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    try:
        w, s, e, n = (float(x) for x in bbox.split(","))
    except ValueError as exc:
        raise AppError(422, "VALIDATION_ERROR", "bbox 형식은 west,south,east,north 입니다.", {"bbox": "숫자 4개"}) from exc
    if not (-180 <= w <= 180 and -180 <= e <= 180 and -90 <= s <= 90 and -90 <= n <= 90 and s <= n):
        raise AppError(422, "VALIDATION_ERROR", "bbox 범위가 올바르지 않습니다.", {"bbox": "범위 오류"})
    return w, s, e, n


def _bbox_filter(b):
    w, s, e, n = b
    lat = Place.latitude.between(s, n)
    if w <= e:
        return and_(lat, Place.longitude.between(w, e))
    return and_(lat, or_(Place.longitude >= w, Place.longitude <= e))  # 날짜 변경선 걸침


class _cell_index(FunctionElement):
    """0 이상인 값의 내림(floor). PostgreSQL은 floor(), SQLite는 수학 함수가 없는 빌드도 있어 정수 변환(양수에서 내림과 같음)."""
    type = Integer()
    inherit_cache = True


@compiles(_cell_index)
def _cell_index_default(element, compiler, **kw):
    return f"floor({compiler.process(element.clauses, **kw)})"


@compiles(_cell_index, "sqlite")
def _cell_index_sqlite(element, compiler, **kw):
    return f"CAST({compiler.process(element.clauses, **kw)} AS INTEGER)"


def get_map(db: Session, viewer: User | None, mode: str, bbox: str | None, zoom: int) -> MapResponse:
    if not 0 <= zoom <= MAX_ZOOM:
        raise AppError(422, "VALIDATION_ERROR", "zoom 범위는 0~20 입니다.", {"zoom": "범위 오류"})
    return _compute(db, viewer, mode, bbox, zoom)


def _compute(db: Session, viewer: User | None, mode: str, bbox: str | None, zoom: int) -> MapResponse:
    mode_cond = map_mode_filter(mode, viewer)
    b = parse_bbox(bbox)
    place_cond = [_bbox_filter(b)] if b else []
    # 장소별 사진 수. 범위(bbox)가 있으면 장소를 먼저 걸러 그 장소의 사진만 세고, 전 지구면 사진만 읽어 센다
    counted = select(Photo.place_id.label("pid"), func.count(Photo.id).label("cnt"))
    if place_cond:
        counted = counted.join(Place, Place.id == Photo.place_id).where(*place_cond)
    per_place = counted.where(mode_cond).group_by(Photo.place_id).subquery()

    if zoom >= PLACE_ZOOM:
        stmt = (
            select(Place.id, Place.name, Place.latitude, Place.longitude, per_place.c.cnt)
            .join(per_place, per_place.c.pid == Place.id)
            .where(*place_cond)
            .order_by(per_place.c.cnt.desc())
            .limit(MAX_ITEMS + 1)
        )
        rows = db.execute(stmt).all()
        items = [MapPlace(place_id=str(r.id), name=r.name, latitude=r.latitude, longitude=r.longitude, photo_count=r.cnt) for r in rows[:MAX_ITEMS]]
        return MapResponse(mode=mode, zoom=zoom, items=items, truncated=len(rows) > MAX_ITEMS)

    # 지리 격자 클러스터. 격자는 경도 -180에서 시작하므로 한 칸이 날짜 변경선을 넘지 않는다 → 칸 안 평균 좌표가 올바름
    cell = 180.0 / (2 ** (zoom + 1))
    ci = _cell_index((Place.latitude + 90) / cell)
    cj = _cell_index((Place.longitude + 180) / cell)
    photos = func.sum(per_place.c.cnt)
    stmt = (
        select(
            ci.label("i"), cj.label("j"), photos.label("photos"), func.count().label("places"),
            (func.sum(Place.latitude * per_place.c.cnt) / photos).label("lat"),
            (func.sum(Place.longitude * per_place.c.cnt) / photos).label("lng"),
            # 칸에 장소가 하나뿐이면 그 장소를 그대로 핀으로 보여 준다
            func.min(cast(Place.id, String)).label("pid"), func.min(Place.name).label("name"),
            func.min(Place.latitude).label("plat"), func.min(Place.longitude).label("plng"),
            func.min(Place.country_code).label("cc_min"), func.max(Place.country_code).label("cc_max"), func.count(Place.country_code).label("cc_n"),
        )
        .join(per_place, per_place.c.pid == Place.id)
        .where(*place_cond)
        .group_by(ci, cj)
        .order_by(photos.desc())
        .limit(MAX_ITEMS + 1)
    )
    rows = db.execute(stmt).all()
    out: list[MapCluster | MapPlace] = []
    for r in rows[:MAX_ITEMS]:
        if r.places == 1:
            out.append(MapPlace(place_id=str(uuid.UUID(str(r.pid))), name=r.name, latitude=r.plat, longitude=r.plng, photo_count=int(r.photos)))
            continue
        same_country = r.cc_n == r.places and r.cc_min == r.cc_max
        out.append(MapCluster(
            id=f"g{zoom}:{int(r.i)}:{int(r.j)}", latitude=round(float(r.lat), 6), longitude=round(float(r.lng), 6),
            photo_count=int(r.photos), place_count=r.places, label=f"{r.cc_min} · {r.places}곳" if same_country else f"{r.places}곳",
        ))
    return MapResponse(mode=mode, zoom=zoom, items=out, truncated=len(rows) > MAX_ITEMS)
