from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.errors import AppError, not_found
from app.core.ratelimit import geocode_limiter
from app.dependencies.auth import require_user
from app.models import User
from app.services.geocode_service import GeocoderUnavailable, GeoResult, get_service

router = APIRouter(prefix="/geocode", tags=["geocode"])


class GeoResultOut(BaseModel):
    name: str
    address: str | None
    latitude: float
    longitude: float
    city: str | None
    country_code: str | None


class GeoSearchOut(BaseModel):
    items: list[GeoResultOut]
    next_cursor: str | None = None
    attribution: str  # 데이터 출처 표시 (OpenStreetMap 라이선스 등)


def _svc():
    svc = get_service()
    if svc is None:
        raise AppError(503, "GEOCODER_DISABLED", "장소 검색 서비스가 꺼져 있습니다. 좌표를 직접 입력해 주세요.")
    return svc


def _out(r: GeoResult) -> GeoResultOut:
    return GeoResultOut(name=r.name, address=r.address, latitude=r.latitude, longitude=r.longitude, city=r.city, country_code=r.country_code)


UNAVAILABLE = AppError(503, "GEOCODER_UNAVAILABLE", "장소 검색 서비스에 연결할 수 없습니다. 잠시 후 다시 시도하거나 지도에서 직접 고르세요.")


@router.get("/search", response_model=GeoSearchOut)
def search(q: str = Query(min_length=1, max_length=100), limit: int = Query(default=5, ge=1, le=10), me: User = Depends(require_user)):
    """주소·장소 이름으로 좌표 찾기. 로그인 사용자만, 사용자당 분당 30회."""
    geocode_limiter.hit(str(me.id))
    svc = _svc()
    try:
        results = svc.search(q, limit)
    except GeocoderUnavailable as e:
        raise UNAVAILABLE from e
    return GeoSearchOut(items=[_out(r) for r in results], attribution=svc.attribution)


@router.get("/reverse", response_model=GeoResultOut)
def reverse(lat: float = Query(ge=-90, le=90), lng: float = Query(ge=-180, le=180), me: User = Depends(require_user)):
    """좌표 → 주소·도시·국가 (새 장소 이름·국가 코드 미리 채우기용)."""
    geocode_limiter.hit(str(me.id))
    svc = _svc()
    try:
        result = svc.reverse(lat, lng)
    except GeocoderUnavailable as e:
        raise UNAVAILABLE from e
    if result is None:
        raise not_found("주소")
    return _out(result)
