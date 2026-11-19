from datetime import timedelta

from sqlalchemy import select

from app.core.database import SessionLocal, utcnow
from app.models import User, UserSession
from tests.conftest import PASSWORD, UserClient, make_client

API = "/api/v1"


def test_register_login_me_logout():
    c = make_client()
    r = c.post(f"{API}/auth/register", json={"email": "New@Example.com", "username": "New_User", "display_name": "새 사용자", "password": PASSWORD})
    assert r.status_code == 201
    assert "email" not in r.json() and "password_hash" not in r.json()
    assert r.json()["username"] == "new_user"

    r = c.post(f"{API}/auth/login", json={"email": "new@example.com", "password": PASSWORD})
    assert r.status_code == 200
    csrf = r.json()["csrf_token"]
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie

    me = c.get(f"{API}/auth/me")
    assert me.status_code == 200 and me.json()["display_name"] == "새 사용자"
    assert me.json()["csrf_token"] == csrf

    assert c.post(f"{API}/auth/logout").status_code == 403  # CSRF 없음
    assert c.post(f"{API}/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert c.get(f"{API}/auth/me").status_code == 401


def test_password_is_hashed():
    UserClient("hashme")
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.username == "hashme"))
        assert PASSWORD not in u.password_hash and u.password_hash.startswith("scrypt$")
        s = db.scalar(select(UserSession).where(UserSession.user_id == u.id))
        assert len(s.token_hash) == 64


def test_duplicates_rejected():
    UserClient("dup")
    c = make_client()
    r = c.post(f"{API}/auth/register", json={"email": "DUP@example.com", "username": "DUP", "display_name": "x", "password": PASSWORD})
    assert r.status_code == 409
    assert set(r.json()["field_errors"]) == {"email", "username"}


def test_validation():
    c = make_client()
    r = c.post(f"{API}/auth/register", json={"email": "bad", "username": "a!", "display_name": "", "password": "short"})
    assert r.status_code == 422
    assert {"email", "username", "display_name", "password"} <= set(r.json()["field_errors"])


def test_login_failure_same_message():
    UserClient("exists")
    c = make_client()
    a = c.post(f"{API}/auth/login", json={"email": "exists@example.com", "password": "wrong-password-123"})
    b = c.post(f"{API}/auth/login", json={"email": "nobody@example.com", "password": "wrong-password-123"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_expired_session():
    u = UserClient("expire")
    with SessionLocal() as db:
        for s in db.scalars(select(UserSession)):
            s.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert u.get(f"{API}/auth/me").status_code == 401


def test_bad_origin_blocked():
    u = UserClient("origin")
    r = u.patch(f"{API}/users/me", json={"bio": "hi"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = u.patch(f"{API}/users/me", json={"bio": "hi"}, headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 200


def test_login_rate_limited():
    c = make_client()
    codes = [c.post(f"{API}/auth/login", json={"email": "x@example.com", "password": "nope-nope-nope"}).status_code for _ in range(11)]
    assert codes[-1] == 429
    # 같은 IP의 다른 사람(다른 이메일)은 막히지 않는다 (학교·회사 공유 IP)
    assert c.post(f"{API}/auth/login", json={"email": "other@example.com", "password": "nope-nope-nope"}).status_code == 401


def test_shared_ip_many_users_can_log_in():
    for i in range(15):
        UserClient(f"student{i}")  # 같은 IP에서 15명 가입·로그인


def test_reserved_usernames_rejected():
    c = make_client()
    for name in ("search", "ME", "settings"):
        r = c.post(f"{API}/auth/register", json={"email": f"{name}@example.com", "username": name, "display_name": "x", "password": PASSWORD})
        assert r.status_code == 422 and "username" in r.json()["field_errors"], name


def test_validation_error_does_not_echo_password():
    c = make_client()
    r = c.post(f"{API}/auth/register", json={"email": "a@example.com", "username": "abc", "display_name": "x", "password": "pw-leak1"})
    assert r.status_code == 422 and "pw-leak1" not in r.text
