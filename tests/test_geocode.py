"""장소 검색(지오코딩) 제공자. 실제 외부 서비스 대신 가짜 HTTP 전송을 쓴다."""
import time

import httpx
import pytest

from app.services import geocode_service
from app.services.geocode_service import GeocodeService, KakaoProvider, NominatimProvider

API = "/api/v1"

NOMINATIM_SEARCH = [{
    "lat": "37.5796", "lon": "126.9770", "name": "경복궁", "display_name": "경복궁, 사직로, 종로구, 서울, 03045, 대한민국",
    "address": {"city": "서울", "country_code": "kr"},
}]
NOMINATIM_REVERSE = {
    "lat": "37.5796", "lon": "126.977", "name": "", "display_name": "사직로 161, 종로구, 서울, 03045, 대한민국",
    "address": {"road": "사직로", "city": "서울", "country_code": "kr"},
}


def nominatim(calls: list, search=NOMINATIM_SEARCH, reverse=NOMINATIM_REVERSE, status=200, min_interval=0.0):
    def handler(request: httpx.Request):
        calls.append(request)
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(200, json=search if request.url.path == "/search" else reverse)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GeocodeService(NominatimProvider("https://nominatim.test", "photo-globe-test", client=client, min_interval=min_interval), ttl_seconds=60)


@pytest.fixture(autouse=True)
def _restore():
    yield
    geocode_service.set_service(None)


def test_search_reverse_cache_and_auth(users, anon):
    a, *_ = users
    calls: list = []
    geocode_service.set_service(nominatim(calls))
    body = a.get(f"{API}/geocode/search", params={"q": "경복궁"}).json()
    item = body["items"][0]
    assert item["name"] == "경복궁" and item["country_code"] == "KR" and item["city"] == "서울"
    assert abs(item["latitude"] - 37.5796) < 1e-9 and "OpenStreetMap" in body["attribution"] and body["next_cursor"] is None
    assert calls[0].headers["user-agent"].startswith("photo-globe") and calls[0].url.params["format"] == "jsonv2"

    a.get(f"{API}/geocode/search", params={"q": "  경복궁 "})
    assert len(calls) == 1  # 같은 검색어는 캐시에서

    rv = a.get(f"{API}/geocode/reverse", params={"lat": 37.5796, "lng": 126.977}).json()
    assert rv["name"] == "사직로 161" and rv["city"] == "서울" and rv["country_code"] == "KR"

    assert anon.get(f"{API}/geocode/search", params={"q": "x"}).status_code == 401
    assert a.get(f"{API}/geocode/reverse", params={"lat": 100, "lng": 0}).status_code == 422


def test_kakao_provider(users):
    a, *_ = users

    def handler(req: httpx.Request):
        assert req.headers["authorization"] == "KakaoAK test-key"
        if req.url.path.endswith("keyword.json"):
            return httpx.Response(200, json={"documents": [{
                "place_name": "가평역", "address_name": "경기 가평군 가평읍 달전리 380",
                "road_address_name": "경기 가평군 가평읍 장터길 1", "x": "127.5089", "y": "37.8147",
            }]})
        return httpx.Response(200, json={"documents": [{
            "address": {"address_name": "경기 가평군 가평읍 달전리 380", "region_1depth_name": "경기", "region_2depth_name": "가평군"},
            "road_address": None,
        }]})

    geocode_service.set_service(GeocodeService(KakaoProvider("test-key", client=httpx.Client(transport=httpx.MockTransport(handler)))))
    item = a.get(f"{API}/geocode/search", params={"q": "가평역"}).json()["items"][0]
    assert item["name"] == "가평역" and item["address"] == "경기 가평군 가평읍 장터길 1" and item["city"] == "경기 가평군" and item["country_code"] == "KR"
    rv = a.get(f"{API}/geocode/reverse", params={"lat": 37.8147, "lng": 127.5089}).json()
    assert rv["address"] == "경기 가평군 가평읍 달전리 380" and rv["city"] == "경기 가평군"


def test_disabled_unavailable_and_not_found(users):
    a, *_ = users
    geocode_service.set_service(None)
    r = a.get(f"{API}/geocode/search", params={"q": "x"})
    assert r.status_code == 503 and r.json()["code"] == "GEOCODER_DISABLED"

    geocode_service.set_service(nominatim([], status=500))
    r = a.get(f"{API}/geocode/search", params={"q": "x"})
    assert r.status_code == 503 and r.json()["code"] == "GEOCODER_UNAVAILABLE"

    def timeout(req):
        raise httpx.ConnectTimeout("slow", request=req)

    geocode_service.set_service(GeocodeService(NominatimProvider("https://n.test", "ua", client=httpx.Client(transport=httpx.MockTransport(timeout)), min_interval=0)))
    assert a.get(f"{API}/geocode/search", params={"q": "y"}).status_code == 503

    geocode_service.set_service(nominatim([], reverse={"error": "Unable to geocode"}))
    assert a.get(f"{API}/geocode/reverse", params={"lat": 0.5, "lng": -30}).status_code == 404


def test_per_user_rate_limit(users):
    a, b, _ = users
    geocode_service.set_service(nominatim([]))
    codes = [a.get(f"{API}/geocode/search", params={"q": f"q{i}"}).status_code for i in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429
    assert b.get(f"{API}/geocode/search", params={"q": "다른 사용자"}).status_code == 200


def test_nominatim_one_request_per_interval():
    calls: list = []
    svc = nominatim(calls, min_interval=0.3)
    t = time.monotonic()
    svc.search("a", 5)
    svc.search("b", 5)
    assert time.monotonic() - t >= 0.3 and len(calls) == 2


def test_nominatim_busy_rejects_instead_of_queueing_forever():
    calls: list = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=[])

    provider = NominatimProvider("https://n.test", "ua", client=httpx.Client(transport=httpx.MockTransport(handler)), min_interval=1.0, max_wait=1.5)
    t = time.monotonic()
    provider.search("a", 1)  # 바로 보냄
    provider.search("b", 1)  # 1초 기다렸다 보냄
    assert provider._reserve() <= 1.5  # 다음 순서(약 1초 뒤)는 예약 가능
    with pytest.raises(geocode_service.GeocoderUnavailable):
        provider._reserve()  # 그다음 순서는 약 2초 뒤 → max_wait(1.5초) 초과 → 줄 세우지 않고 바로 거절
    assert len(calls) == 2 and time.monotonic() - t < 2.5
