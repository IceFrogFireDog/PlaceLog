"""계정 삭제(탈퇴)."""
import uuid

from sqlalchemy import func, or_, select

from app.core.database import SessionLocal
from app.models import EmailToken, Friendship, Photo, Place, User, UserSession
from app.services.storage_service import get_storage
from tests.conftest import PASSWORD, UserClient, befriend, create_place, jpeg_bytes, make_client, register_payload, upload

API = "/api/v1"


def delete_me(client, password):
    return client.request("DELETE", f"{API}/users/me", json={"password": password})


def test_delete_account_removes_user_data(users, anon):
    a, b, c = users
    a.put(f"{API}/users/me/avatar", files={"file": ("me.jpg", jpeg_bytes(), "image/jpeg")})
    own_only = create_place(a, "혼자 쓰는 장소", 37.1, 127.1)
    upload(a, own_only, "PUBLIC")
    shared = create_place(a, "함께 쓰는 장소", 37.2, 127.2)
    upload(a, shared, "PUBLIC")
    upload(b, shared, "PUBLIC")
    b_place = create_place(b, "밥의 장소", 37.3, 127.3)
    upload(b, b_place, "PUBLIC")  # 사진이 있어야 다른 사람에게 보이는 장소가 된다
    in_b_place = upload(a, b_place, "PUBLIC").json()["id"]
    befriend(a, b)
    c.post(f"{API}/friends/requests", json={"target_user_id": a.id})
    storage = get_storage()
    assert len(list(storage.list_keys(f"photos/{a.id}/"))) == 9 and list(storage.list_keys(f"avatars/{a.id}/"))

    r = delete_me(a, "wrong-password-1")
    assert r.status_code == 422 and "password" in r.json()["field_errors"]
    assert delete_me(a, "").status_code == 422
    assert anon.request("DELETE", f"{API}/users/me", json={"password": PASSWORD}).status_code == 401

    r = delete_me(a, PASSWORD)
    assert r.status_code == 204 and "pg_session=" in r.headers.get("set-cookie", "")
    assert a.get(f"{API}/auth/me").status_code == 401

    uid = uuid.UUID(a.id)
    with SessionLocal() as db:
        assert db.get(User, uid) is None
        assert db.scalar(select(func.count()).select_from(Photo).where(Photo.user_id == uid)) == 0
        assert db.scalar(select(func.count()).select_from(Friendship).where(or_(Friendship.user_low_id == uid, Friendship.user_high_id == uid))) == 0
        assert db.scalar(select(func.count()).select_from(UserSession).where(UserSession.user_id == uid)) == 0
        assert db.scalar(select(func.count()).select_from(EmailToken).where(EmailToken.user_id == uid)) == 0
        assert db.get(Place, uuid.UUID(own_only)) is None  # 사진이 하나도 남지 않은 내 장소는 삭제
        kept = db.get(Place, uuid.UUID(shared))
        assert kept is not None and kept.created_by is None  # 다른 사람 사진이 있는 장소는 공유 장소로 남음
        assert db.get(Place, uuid.UUID(b_place)) is not None
    assert list(storage.list_keys(f"photos/{a.id}/")) == [] and list(storage.list_keys(f"avatars/{a.id}/")) == []

    assert anon.get(f"{API}/users/alice").status_code == 404
    assert anon.get(f"{API}/photos/{in_b_place}").status_code == 404
    assert b.get(f"{API}/places/{shared}").json()["photo_count"] == 1
    assert b.get(f"{API}/friends").json()["items"] == []
    assert c.get(f"{API}/friends/requests", params={"direction": "outgoing"}).json()["items"] == []

    # 같은 이메일·닉네임으로 다시 가입할 수 있다
    assert make_client().post(f"{API}/auth/register", json=register_payload("alice")).status_code == 201


def test_delete_account_logs_out_every_device_and_is_rate_limited():
    u = UserClient("leaver")
    other = make_client()
    assert other.post(f"{API}/auth/login", json={"email": u.email, "password": PASSWORD}).status_code == 200
    codes = [delete_me(u, f"wrong-password-{i}").status_code for i in range(11)]
    assert codes[:10] == [422] * 10 and codes[10] == 429
    assert other.get(f"{API}/auth/me").status_code == 200  # 실패한 시도로는 아무것도 지워지지 않음


def test_delete_account_requires_csrf():
    u = UserClient("csrfcheck")
    del u.c.headers["X-CSRF-Token"]
    assert delete_me(u, PASSWORD).status_code == 403
