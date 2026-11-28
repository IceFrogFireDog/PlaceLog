"""관리자 기능."""
import uuid

from app.core.database import SessionLocal
from app.models import Place
from app.services.storage_service import get_storage
from app.tasks import main as tasks_main
from tests.conftest import PASSWORD, UserClient, create_place, make_client, upload

API = "/api/v1"


def make_admin(u: UserClient) -> None:
    assert tasks_main(["make-admin", u.email]) == 0


def test_admin_endpoints_hidden_from_others(users, anon):
    a, *_ = users
    for c in (anon, a):
        assert c.get(f"{API}/admin/stats").status_code in (401, 404)
        assert c.get(f"{API}/admin/users").status_code in (401, 404)
    assert a.get(f"{API}/admin/stats").status_code == 404  # 일반 사용자에게는 존재 자체를 숨김
    assert a.get(f"{API}/auth/me").json()["is_admin"] is False


def test_stats_and_user_search(users, capsys):
    a, b, _ = users
    make_admin(a)
    assert "주었습니다" in capsys.readouterr().out
    assert a.get(f"{API}/auth/me").json()["is_admin"] is True
    upload(b, create_place(b), "PUBLIC")
    st = a.get(f"{API}/admin/stats").json()
    assert st["users"] == 3 and st["photos"]["READY"] == 1 and st["places"] == 1
    page = a.get(f"{API}/admin/users", params={"q": "bob"}).json()
    assert [u["username"] for u in page["items"]] == ["bob"] and page["items"][0]["photo_count"] == 1
    assert tasks_main(["make-admin", a.email, "--revoke"]) == 0
    assert a.get(f"{API}/admin/stats").status_code == 404


def test_suspend_blocks_login_and_existing_sessions(users):
    a, b, _ = users
    make_admin(a)
    r = a.post(f"{API}/admin/users/{b.id}/suspend", json={"suspended": True})
    assert r.status_code == 200 and r.json()["suspended"] is True
    assert b.get(f"{API}/auth/me").status_code == 401  # 남은 세션도 바로 끊김
    r = make_client().post(f"{API}/auth/login", json={"email": b.email, "password": PASSWORD})
    assert r.status_code == 403 and r.json()["code"] == "ACCOUNT_SUSPENDED"
    assert make_client().post(f"{API}/auth/login", json={"email": b.email, "password": "wrong-password-1"}).status_code == 401  # 비밀번호가 틀리면 정지 여부도 알려 주지 않음
    assert a.post(f"{API}/admin/users/{a.id}/suspend", json={"suspended": True}).status_code == 422  # 자기 자신은 안 됨
    a.post(f"{API}/admin/users/{b.id}/suspend", json={"suspended": False})
    assert make_client().post(f"{API}/auth/login", json={"email": b.email, "password": PASSWORD}).status_code == 200


def test_admin_deletes_reported_photo(users, anon):
    a, b, _ = users
    make_admin(a)
    phid = upload(b, create_place(b), "PUBLIC").json()["id"]
    assert a.delete(f"{API}/photos/{phid}").status_code == 403  # 일반 삭제는 작성자만
    assert a.delete(f"{API}/admin/photos/{phid}").status_code == 204
    assert anon.get(f"{API}/photos/{phid}").status_code == 404
    assert list(get_storage().list_keys(f"photos/{b.id}/{phid}/")) == []


def test_duplicate_places_merge(users):
    a, b, _ = users
    make_admin(a)
    p1 = create_place(b, "남산타워", 37.5512, 126.9882)
    p2 = b.post(f"{API}/places", json={"name": "남산 타워", "latitude": 37.5513, "longitude": 126.9883, "force": True}).json()["id"]
    upload(b, p1, "PUBLIC")
    upload(b, p2, "PUBLIC")
    pairs = a.get(f"{API}/admin/places/duplicates").json()
    assert len(pairs) == 1 and {pairs[0]["a"]["id"], pairs[0]["b"]["id"]} == {p1, p2} and pairs[0]["distance_m"] < 50
    assert a.post(f"{API}/admin/places/merge", json={"source_id": p2, "target_id": p2}).status_code == 422
    assert a.post(f"{API}/admin/places/merge", json={"source_id": p2, "target_id": p1}).json() == {"moved": 1}
    with SessionLocal() as db:
        assert db.get(Place, uuid.UUID(p2)) is None
    assert a.get(f"{API}/admin/places/duplicates").json() == []
