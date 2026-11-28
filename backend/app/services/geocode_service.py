"""장소 검색(지오코딩) 제공자 어댑터.
GEOCODER=nominatim (기본, 키 불필요, OpenStreetMap 데이터) / kakao (국내 검색 품질 좋음, KAKAO_REST_API_KEY 필요) / none.
브라우저가 외부 서비스를 직접 부르지 않고 백엔드를 거친다 → 키 보호, 캐시, 제공자 이용 정책(초당 1회 등) 준수."""
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

import httpx

from app.core.config import settings


@dataclass
class GeoResult:
    name: str
    address: str | None
    latitude: float
    longitude: float
    city: str | None
    country_code: str | None


class GeocoderUnavailable(Exception):
    pass


def _clip(v: str | None, n: int) -> str | None:
    v = (v or "").strip()
    return v[:n] if v else None


class NominatimProvider:
    """OpenStreetMap Nominatim. 이용 정책: 초당 1회 이하, 앱을 식별하는 User-Agent, 결과 캐시 권장."""

    attribution = "© OpenStreetMap contributors (ODbL)"

    def __init__(self, base_url: str, user_agent: str, client: httpx.Client | None = None, min_interval: float = 1.0, max_wait: float = 3.0):
        self.base = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=6.0)
        self.headers = {"User-Agent": user_agent, "Accept-Language": "ko,en"}
        self.min_interval = min_interval
        self.max_wait = max_wait
        self._lock = threading.Lock()
        self._next = 0.0  # 다음 요청을 보내도 되는 시각

    def _reserve(self) -> float:
        """초당 1회 순서표를 받는다. 기다릴 시간이 max_wait을 넘으면 줄을 세우지 않고 바로 거절한다
        (요청이 몰릴 때 작업 스레드가 잠든 채 쌓여 다른 API까지 느려지는 것을 막는다)."""
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next)
            if slot - now > self.max_wait:
                raise GeocoderUnavailable("busy")
            self._next = slot + self.min_interval
            return slot - now

    def _get(self, path: str, params: dict):
        wait = self._reserve()
        if wait > 0:
            time.sleep(wait)
        try:
            r = self.client.get(f"{self.base}{path}", params=params, headers=self.headers)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise GeocoderUnavailable(type(e).__name__) from e

    @staticmethod
    def _parse(item: dict) -> GeoResult:
        addr = item.get("address") or {}
        display = item.get("display_name") or ""
        name = item.get("name") or display.split(",")[0]
        city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county") or addr.get("state")
        cc = (addr.get("country_code") or "")[:2].upper() or None
        return GeoResult(
            name=_clip(name, 120) or _clip(display, 120) or "이름 없는 장소", address=_clip(display, 300),
            latitude=float(item["lat"]), longitude=float(item["lon"]), city=_clip(city, 120), country_code=cc,
        )

    def search(self, q: str, limit: int) -> list[GeoResult]:
        data = self._get("/search", {"q": q, "format": "jsonv2", "limit": limit, "addressdetails": 1})
        try:
            return [self._parse(it) for it in data][:limit]
        except (KeyError, TypeError, ValueError) as e:
            raise GeocoderUnavailable("bad response") from e

    def reverse(self, lat: float, lng: float) -> GeoResult | None:
        data = self._get("/reverse", {"lat": lat, "lon": lng, "format": "jsonv2", "addressdetails": 1, "zoom": 18})
        if not isinstance(data, dict) or "error" in data or "lat" not in data:
            return None
        try:
            return self._parse(data)
        except (KeyError, TypeError, ValueError) as e:
            raise GeocoderUnavailable("bad response") from e


class KakaoProvider:
    """카카오 로컬 API (국내 장소·주소). 키는 서버에만 둔다."""

    attribution = "Kakao 로컬 API"
    base = "https://dapi.kakao.com"

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=6.0)
        self.headers = {"Authorization": f"KakaoAK {api_key}"}

    def _get(self, path: str, params: dict) -> dict:
        try:
            r = self.client.get(f"{self.base}{path}", params=params, headers=self.headers)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise GeocoderUnavailable(type(e).__name__) from e

    def search(self, q: str, limit: int) -> list[GeoResult]:
        data = self._get("/v2/local/search/keyword.json", {"query": q, "size": min(limit, 15)})
        out = []
        try:
            for d in data.get("documents", [])[:limit]:
                addr = d.get("road_address_name") or d.get("address_name")
                tokens = (d.get("address_name") or "").split()
                out.append(GeoResult(
                    name=_clip(d.get("place_name"), 120) or "이름 없는 장소", address=_clip(addr, 300),
                    latitude=float(d["y"]), longitude=float(d["x"]), city=_clip(" ".join(tokens[:2]), 120), country_code="KR",
                ))
        except (KeyError, TypeError, ValueError) as e:
            raise GeocoderUnavailable("bad response") from e
        return out

    def reverse(self, lat: float, lng: float) -> GeoResult | None:
        data = self._get("/v2/local/geo/coord2address.json", {"x": lng, "y": lat})
        docs = data.get("documents") or []
        if not docs:
            return None
        doc = docs[0]
        road, addr = doc.get("road_address") or {}, doc.get("address") or {}
        full = road.get("address_name") or addr.get("address_name")
        city = " ".join(x for x in (addr.get("region_1depth_name"), addr.get("region_2depth_name")) if x)
        return GeoResult(
            name=_clip(road.get("building_name") or full, 120) or "이름 없는 장소", address=_clip(full, 300),
            latitude=lat, longitude=lng, city=_clip(city, 120), country_code="KR",
        )


class GeocodeService:
    """제공자 앞에 TTL 캐시를 둔다 (같은 검색어 반복 호출 방지)."""

    def __init__(self, provider, ttl_seconds: int = 86400, max_entries: int = 2000):
        self.provider = provider
        self.ttl = ttl_seconds
        self.max = max_entries
        self._cache: OrderedDict[tuple, tuple[float, object]] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def attribution(self) -> str:
        return self.provider.attribution

    def _cached(self, key: tuple, fn):
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] > now:
                self._cache.move_to_end(key)
                return hit[1]
        value = fn()
        if self.ttl > 0:
            with self._lock:
                self._cache[key] = (now + self.ttl, value)
                self._cache.move_to_end(key)
                while len(self._cache) > self.max:
                    self._cache.popitem(last=False)
        return value

    def search(self, q: str, limit: int) -> list[GeoResult]:
        q = " ".join(q.split())
        return self._cached(("s", q.casefold(), limit), lambda: self.provider.search(q, limit))

    def reverse(self, lat: float, lng: float) -> GeoResult | None:
        lat, lng = round(lat, 5), round(lng, 5)  # 약 1m 단위로 캐시
        return self._cached(("r", lat, lng), lambda: self.provider.reverse(lat, lng))


_service: GeocodeService | None = None
_configured = False


def get_service() -> GeocodeService | None:
    global _service, _configured
    if not _configured:
        _configured = True
        if settings.geocoder == "nominatim":
            ua = settings.geocoder_user_agent + (f" ({settings.geocoder_contact_email})" if settings.geocoder_contact_email else "")
            _service = GeocodeService(NominatimProvider(settings.nominatim_base_url, ua), settings.geocode_cache_seconds)
        elif settings.geocoder == "kakao":
            _service = GeocodeService(KakaoProvider(settings.kakao_rest_api_key), settings.geocode_cache_seconds)
    return _service


def set_service(s: GeocodeService | None) -> None:  # 테스트용
    global _service, _configured
    _service, _configured = s, True
