"""공유 장소 중복 정리 정책."""
from app.services.place_service import normalize_name
from tests.conftest import create_place, upload

API = "/api/v1"


def test_same_name_nearby_is_409_with_existing(users):
    a, b, _ = users
    pid = create_place(a, "경복궁", 37.5796, 126.9770)
    upload(a, pid, "PUBLIC")
    r = b.post(f"{API}/places", json={"name": " 경복궁 ", "latitude": 37.5797, "longitude": 126.9771})
    assert r.status_code == 409 and r.json()["code"] == "DUPLICATE_PLACE"
    assert r.json()["existing_place"]["id"] == pid and "경복궁" in r.json()["message"]

    r = b.post(f"{API}/places", json={"name": "경복궁 매표소", "latitude": 37.5797, "longitude": 126.9771})
    assert r.status_code == 201 and [c["id"] for c in r.json()["nearby_candidates"]] == [pid]  # 이름이 다르면 안내만

    r = b.post(f"{API}/places", json={"name": "경복궁", "latitude": 37.5797, "longitude": 126.9771, "force": True})
    assert r.status_code == 201  # 확인 후 강제 생성

    assert b.post(f"{API}/places", json={"name": "경복궁", "latitude": 35.0, "longitude": 129.0}).status_code == 201  # 멀면 다른 장소


def test_own_duplicate_also_detected(users):
    a, *_ = users
    create_place(a, "동네 카페", 37.5, 127.0)
    r = a.post(f"{API}/places", json={"name": "동네카페", "latitude": 37.5001, "longitude": 127.0001})
    assert r.status_code == 409


def test_hidden_place_not_revealed_by_duplicate_check(users):
    a, b, _ = users
    pid = create_place(a, "우리집", 37.1234, 127.5678)
    upload(a, pid, "PRIVATE")
    r = b.post(f"{API}/places", json={"name": "우리집", "latitude": 37.1234, "longitude": 127.5678})
    assert r.status_code == 201 and r.json()["nearby_candidates"] == []  # 남의 비공개 장소 존재를 알 수 없음


def test_name_normalization():
    assert normalize_name("Seoul  Tower") == normalize_name("seoul tower") == normalize_name("ＳＥＯＵＬ　ＴＯＷＥＲ")
    assert normalize_name("N서울타워") == normalize_name("N 서울 타워") == normalize_name("n서울-타워!")
    assert normalize_name("경복궁") != normalize_name("창덕궁")
