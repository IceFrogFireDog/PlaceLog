from tests.conftest import create_place, rand_uuid, upload

API = "/api/v1"


EXPECT = {  # 조회자 → 허용되는 공개범위
    "anon": {"PUBLIC"},
    "owner": {"PUBLIC", "FRIENDS", "PRIVATE"},
    "friend": {"PUBLIC", "FRIENDS"},
    "pending": {"PUBLIC"},
}


def test_matrix_detail_media_lists(world):
    a, b, c, anon, pid, photos = world
    viewers = {"anon": anon, "owner": a, "friend": b, "pending": c}
    for name, cl in viewers.items():
        allowed = EXPECT[name]
        for vis, phid in photos.items():
            code = 200 if vis in allowed else 404
            assert cl.get(f"{API}/photos/{phid}").status_code == code, (name, vis)
            for variant in ("thumbnail", "display"):
                r = cl.get(f"{API}/media/{phid}/{variant}")
                assert r.status_code == code, (name, vis, variant)
                if code == 200:
                    assert "no-store" in r.headers["cache-control"]
        # 장소 목록·개수
        listed = {p["visibility"] for p in cl.get(f"{API}/places/{pid}/photos").json()["items"]}
        assert listed == allowed, name
        assert cl.get(f"{API}/places/{pid}").json()["photo_count"] == len(allowed)
        # 프로필 목록·통계
        assert {p["visibility"] for p in cl.get(f"{API}/users/alice/photos").json()["items"]} == allowed
        prof = cl.get(f"{API}/users/alice").json()
        assert prof["photo_count"] == len(allowed)
        assert (prof["friend_count"] is not None) == (name == "owner")


def test_original_owner_only(world):
    a, b, _, anon, _, photos = world
    phid = photos["PUBLIC"]
    assert a.get(f"{API}/media/{phid}/original").status_code == 200
    assert b.get(f"{API}/media/{phid}/original").status_code == 404
    assert anon.get(f"{API}/media/{phid}/original").status_code == 404
    assert b.get(f"{API}/photos/{phid}").json()["original_url"] is None


def test_edit_delete_owner_only(world):
    a, b, _, anon, _, photos = world
    phid = photos["PUBLIC"]
    assert b.patch(f"{API}/photos/{phid}", json={"caption": "hack"}).status_code == 403
    assert b.delete(f"{API}/photos/{phid}").status_code == 403
    assert anon.delete(f"{API}/photos/{phid}").status_code == 401
    assert b.patch(f"{API}/photos/{photos['PRIVATE']}", json={"caption": "x"}).status_code == 404
    r = a.patch(f"{API}/photos/{phid}", json={"caption": "수정됨"})
    assert r.status_code == 200 and r.json()["caption"] == "수정됨"
    assert a.delete(f"{API}/photos/{phid}").status_code == 204
    assert a.get(f"{API}/photos/{phid}").status_code == 404
    assert a.get(f"{API}/media/{phid}/thumbnail").status_code == 404


def test_unfriend_and_visibility_change_apply_next_request(world):
    a, b, _, _, _, photos = world
    fphoto = photos["FRIENDS"]
    assert b.get(f"{API}/photos/{fphoto}").status_code == 200
    fid = a.get(f"{API}/friends").json()["items"][0]["id"]
    assert a.delete(f"{API}/friends/{fid}").status_code == 204
    assert b.get(f"{API}/photos/{fphoto}").status_code == 404
    assert b.get(f"{API}/media/{fphoto}/display").status_code == 404

    pub = photos["PUBLIC"]
    assert a.patch(f"{API}/photos/{pub}", json={"visibility": "PRIVATE"}).status_code == 200
    assert b.get(f"{API}/photos/{pub}").status_code == 404


def test_exact_location_rules(users):
    a, b, _ = users
    pid = create_place(a)
    hidden = upload(a, pid, "PUBLIC", shot_latitude=37.1, shot_longitude=127.1).json()["id"]
    shared = upload(a, pid, "PUBLIC", shot_latitude=37.2, shot_longitude=127.2, share_exact_location=True).json()["id"]
    assert b.get(f"{API}/photos/{hidden}").json()["shot_latitude"] is None
    assert a.get(f"{API}/photos/{hidden}").json()["shot_latitude"] == 37.1
    assert b.get(f"{API}/photos/{shared}").json()["shot_latitude"] == 37.2


def test_pagination(users):
    a, *_ = users
    pid = create_place(a)
    ids = {upload(a, pid, "PUBLIC").json()["id"] for _ in range(5)}
    seen, cursor = [], None
    while True:
        q = "?limit=2" + (f"&cursor={cursor}" if cursor else "")
        page = a.get(f"{API}/places/{pid}/photos{q}").json()
        seen += [p["id"] for p in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == 5 and set(seen) == ids


def test_bad_cursor_is_422_not_500(users):
    import base64
    a, *_ = users
    pid = create_place(a)
    naive = base64.urlsafe_b64encode(f"2030-01-01T00:00:00|{rand_uuid()}".encode()).decode()
    for bad in (naive, "garbage!!", base64.urlsafe_b64encode(b"o:-5").decode()):
        assert a.get(f"{API}/places/{pid}/photos?cursor={bad}").status_code == 422
    assert a.get(f"{API}/places?cursor=garbage").status_code == 422


def test_private_only_place_not_leaked(users, anon):
    """PRIVATE 사진만 있는 장소의 이름·좌표가 검색·상세·근처 후보로 새지 않아야 한다."""
    a, b, _ = users
    home = create_place(a, "우리집", 37.1234, 127.5678, "KR")
    upload(a, home, "PRIVATE")
    for cl in (anon, b):
        assert cl.get(f"{API}/places?q=우리").json()["items"] == []
        assert cl.get(f"{API}/places/{home}").status_code == 404
        assert cl.get(f"{API}/places/{home}/photos").status_code == 404
    r = b.post(f"{API}/places", json={"name": "옆집", "latitude": 37.1234, "longitude": 127.5678})
    assert r.json()["nearby_candidates"] == []
    # 남의 숨겨진 장소에 사진을 붙여 노출시킬 수 없다
    assert upload(b, home, "PUBLIC").status_code == 422
    # 본인은 사진이 없어도 자신이 만든 장소를 찾고 볼 수 있다
    assert [p["name"] for p in a.get(f"{API}/places?q=우리").json()["items"]] == ["우리집"]
    # 공개 사진이 생기면 다른 사람에게도 보인다
    upload(a, home, "PUBLIC")
    assert [p["name"] for p in anon.get(f"{API}/places?q=우리").json()["items"]] == ["우리집"]
    assert anon.get(f"{API}/places/{home}").json()["photo_count"] == 1
