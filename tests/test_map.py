from tests.conftest import befriend, create_place, upload

API = "/api/v1"


def _places(client, mode="WORLD", zoom=8, bbox=None):
    q = f"{API}/map/places?mode={mode}&zoom={zoom}" + (f"&bbox={bbox}" if bbox else "")
    r = client.get(q)
    assert r.status_code == 200, r.text
    return {i["name"]: i["photo_count"] for i in r.json()["items"] if i["kind"] == "place"}


def test_modes_and_counts(users, anon):
    a, b, c = users
    befriend(a, b)
    seoul = create_place(a, "서울", 37.5665, 126.978, "KR")
    kyoto = create_place(a, "교토", 35.0116, 135.7681, "JP")
    secret = create_place(a, "비밀", 10, 10, None)
    upload(a, seoul, "PUBLIC"); upload(a, seoul, "FRIENDS"); upload(a, seoul, "PRIVATE")
    upload(a, kyoto, "FRIENDS")
    upload(a, secret, "PRIVATE")

    assert _places(anon) == {"서울": 1}  # PRIVATE만 있는 장소는 WORLD 핀 없음
    assert _places(b, "FRIENDS") == {"서울": 2, "교토": 1}
    assert _places(c, "FRIENDS") == {}
    assert _places(a, "ME") == {"서울": 3, "교토": 1, "비밀": 1}
    assert anon.get(f"{API}/map/places?mode=FRIENDS").status_code == 401
    assert anon.get(f"{API}/map/places?mode=ME").status_code == 401


def test_bbox_and_dateline(users):
    a, *_ = users
    fiji = create_place(a, "피지", -17.7, 178.0, "FJ")
    samoa = create_place(a, "사모아", -13.8, -171.8, "WS")
    seoul = create_place(a, "서울")
    for p in (fiji, samoa, seoul):
        upload(a, p, "PUBLIC")
    assert set(_places(a, bbox="170,-30,-160,0")) == {"피지", "사모아"}  # west > east
    assert set(_places(a, bbox="120,30,135,40")) == {"서울"}
    assert set(_places(a)) == {"피지", "사모아", "서울"}
    assert a.get(f"{API}/map/places?bbox=1,2,3").status_code == 422
    assert a.get(f"{API}/map/places?bbox=0,50,10,40").status_code == 422
    assert a.get(f"{API}/map/places?zoom=99").status_code == 422


def test_clusters_low_zoom(users):
    a, *_ = users
    for i in range(3):
        upload(a, create_place(a, f"서울{i}", 37.5 + i * 0.01, 127.0, "KR"), "PUBLIC")
    upload(a, create_place(a, "수동", -40.0, -40.0, None), "PUBLIC")
    items = a.get(f"{API}/map/places?mode=WORLD&zoom=1").json()["items"]
    clusters = [i for i in items if i["kind"] == "cluster"]
    assert len(clusters) == 1 and clusters[0]["place_count"] == 3 and clusters[0]["photo_count"] == 3
    assert clusters[0]["label"].startswith("KR")
    assert any(i["kind"] == "place" and i["name"] == "수동" for i in items)  # 국가 없는 위치도 포함


def test_response_cap(users, monkeypatch):
    from app.services import map_service

    a, *_ = users
    monkeypatch.setattr(map_service, "MAX_ITEMS", 2)
    for i in range(3):
        upload(a, create_place(a, f"p{i}", i, i), "PUBLIC")
    r = a.get(f"{API}/map/places?zoom=10").json()
    assert len(r["items"]) == 2 and r["truncated"] is True
