"""테스트 DB는 개발 DB와 분리한다. TEST_DATABASE_URL(PostgreSQL 권장)이 없으면 임시 SQLite를 사용."""
import os
import tempfile
import uuid

_tmp = tempfile.mkdtemp(prefix="pg-test-")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["SECRET_KEY"] = "test-secret-key-" + "x" * 32
os.environ["COOKIE_SECURE"] = "false"
os.environ["ALLOWED_ORIGINS"] = "http://localhost:3000"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import Base, engine  # noqa: E402
from app.core.ratelimit import reset_all  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
import app.models as _models  # noqa: E402,F401

PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def _db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    reset_all()
    yield


def make_client() -> TestClient:
    return TestClient(fastapi_app)


def register_payload(username: str, **over) -> dict:
    return {"email": f"{username}@example.com", "username": username, "display_name": username.upper(), "password": PASSWORD, **over}


class UserClient:
    def __init__(self, username: str):
        self.username = username
        self.email = f"{username}@example.com"
        self.c = make_client()
        r = self.c.post("/api/v1/auth/register", json=register_payload(username))
        assert r.status_code == 201, r.text
        self.id = r.json()["id"]
        r = self.c.post("/api/v1/auth/login", json={"email": f"{username}@example.com", "password": PASSWORD})
        assert r.status_code == 200, r.text
        self.c.headers["X-CSRF-Token"] = r.json()["csrf_token"]

    def __getattr__(self, name):
        return getattr(self.c, name)


@pytest.fixture
def users():
    return UserClient("alice"), UserClient("bob"), UserClient("carol")


@pytest.fixture
def anon():
    return make_client()


def befriend(a: UserClient, b: UserClient) -> str:
    r = a.post("/api/v1/friends/requests", json={"target_user_id": b.id})
    assert r.status_code == 201, r.text
    fid = r.json()["id"]
    r = b.post(f"/api/v1/friends/{fid}/accept")
    assert r.status_code == 200, r.text
    return fid


def rand_uuid() -> str:
    return str(uuid.uuid4())
