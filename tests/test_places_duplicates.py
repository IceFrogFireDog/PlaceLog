"""공유 장소: 새 장소를 만들 때 근처의 기존 장소를 후보로 안내한다."""
from tests.conftest import create_place, upload

API = "/api/v1"


def test_nearby_places_suggested(users):
    a, b, _ = users
    pid = create_place(a, "경복궁", 37.5796, 126.9770)
    upload(a, pid, "PUBLIC")
    r = b.post(f"{API}/places", json={"name": "경복궁 매표소", "latitude": 37.5797, "longitude": 126.9771})
    assert r.status_code == 201 and [c["id"] for c in r.json()["nearby_candidates"]] == [pid]  # 200m 안 → 후보로 안내
    r = b.post(f"{API}/places", json={"name": "해운대", "latitude": 35.1587, "longitude": 129.1604})
    assert r.status_code == 201 and r.json()["nearby_candidates"] == []  # 멀면 후보 없음


def test_hidden_place_not_revealed_as_candidate(users):
    a, b, _ = users
    pid = create_place(a, "우리집", 37.1234, 127.5678)
    upload(a, pid, "PRIVATE")
    r = b.post(f"{API}/places", json={"name": "우리집", "latitude": 37.1234, "longitude": 127.5678})
    assert r.status_code == 201 and r.json()["nearby_candidates"] == []  # 남의 비공개 장소 존재를 알 수 없음
    # 본인에게는 자기 장소가 후보로 보인다
    r = a.post(f"{API}/places", json={"name": "우리집 앞", "latitude": 37.1235, "longitude": 127.5679})
    assert [c["id"] for c in r.json()["nearby_candidates"]] == [pid]
