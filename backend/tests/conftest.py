"""테스트 DB는 개발 DB와 분리한다. TEST_DATABASE_URL(PostgreSQL 권장)이 없으면 임시 SQLite를 사용."""
import io
import os
import shutil
import tempfile
import uuid

_tmp = tempfile.mkdtemp(prefix="pg-test-")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["SECRET_KEY"] = "test-secret-key-" + "x" * 32
os.environ["COOKIE_SECURE"] = "false"
os.environ["ALLOWED_ORIGINS"] = "http://localhost:3000"
os.environ["LOCAL_STORAGE_PATH"] = f"{_tmp}/storage"
os.environ["MAX_UPLOAD_BYTES"] = str(2 * 1024 * 1024)
os.environ["MAX_IMAGE_PIXELS"] = "4000000"
os.environ["MAX_RAW_UPLOAD_BYTES"] = str(4 * 1024 * 1024)
os.environ["MAP_CACHE_SECONDS"] = "0"  # 테스트는 지구본 결과를 바로 확인
os.environ["MAIL_BACKEND"] = "file"
os.environ["MAIL_FILE_DIR"] = f"{_tmp}/mail"
os.environ["FRONTEND_BASE_URL"] = "http://localhost:3000"
os.environ["GEOCODER"] = "none"  # 외부 서비스 호출 금지. 지오코딩 테스트는 가짜 전송으로 주입
os.environ["STORAGE_BACKEND"] = "local"
os.environ["RATE_LIMIT_BACKEND"] = "memory"

import email  # noqa: E402
import re  # noqa: E402
from email import policy  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import ExifTags, Image  # noqa: E402
from sqlalchemy import update  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import Base, SessionLocal, engine, utcnow  # noqa: E402
from app.core.ratelimit import reset_all  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
import app.models as _models  # noqa: E402,F401
from app.models import User  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def _db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    reset_all()
    for f in Path(settings.mail_file_dir).glob("*.eml"):
        f.unlink()
    # 테스트마다 사진 저장 폴더도 비운다 (이전 테스트의 파일이 정리 작업 결과에 섞이지 않게)
    shutil.rmtree(settings.local_storage_path, ignore_errors=True)
    Path(settings.local_storage_path).mkdir(parents=True, exist_ok=True)
    yield


def make_client() -> TestClient:
    return TestClient(fastapi_app)


def register_payload(username: str, **over) -> dict:
    return {"email": f"{username}@example.com", "username": username, "display_name": username.upper(), "password": PASSWORD, "agree_privacy": True, **over}


def mark_verified(user_id: str) -> None:
    with SessionLocal() as db:
        db.execute(update(User).where(User.id == uuid.UUID(user_id)).values(email_verified_at=utcnow()))
        db.commit()


def read_mails(to: str) -> list[email.message.EmailMessage]:
    """개발용 파일 메일함에서 받는 사람이 to인 메일 (오래된 것부터)."""
    out = []
    for f in sorted(Path(settings.mail_file_dir).glob("*.eml"), key=lambda p: (p.stat().st_mtime, p.name)):
        msg = email.message_from_bytes(f.read_bytes(), policy=policy.default)
        if msg["To"] == to:
            out.append(msg)
    return out


def last_link(to: str, path: str) -> str:
    """to에게 간 메일 중 /path?token=… 링크가 든 가장 최근 메일의 토큰."""
    pattern = re.compile(rf"{re.escape(path)}\?token=([A-Za-z0-9_\-]+)")
    for msg in reversed(read_mails(to)):
        m = pattern.search(msg.get_content())
        if m:
            return m.group(1)
    raise AssertionError(f"{to}에게 {path} 링크 메일이 없습니다")


class UserClient:
    def __init__(self, username: str, verified: bool = True):
        self.username = username
        self.email = f"{username}@example.com"
        self.c = make_client()
        r = self.c.post("/api/v1/auth/register", json=register_payload(username))
        assert r.status_code == 201, r.text
        self.id = r.json()["id"]
        if verified:
            mark_verified(self.id)
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


@pytest.fixture
def world(users, anon):
    """A=작성자, B=A와 수락된 친구, C=A에게 신청 중(미수락). A의 장소에 PUBLIC/FRIENDS/PRIVATE 사진 1장씩."""
    a, b, c = users
    befriend(a, b)
    assert c.post("/api/v1/friends/requests", json={"target_user_id": a.id}).status_code == 201
    pid = create_place(a)
    photos = {v: upload(a, pid, v).json()["id"] for v in ("PUBLIC", "FRIENDS", "PRIVATE")}
    return a, b, c, anon, pid, photos


def jpeg_bytes(size=(64, 48), gps: tuple[float, float] | None = None, dt: str | None = None, offset: str | None = None, orientation: int | None = None) -> bytes:
    img = Image.new("RGB", size, (200, 80, 40))
    exif = Image.Exif()
    exif[0x010F] = "TestMake"
    exif[0x0110] = "TestCam 1"
    if orientation:
        exif[0x0112] = orientation
    ifd = exif.get_ifd(ExifTags.IFD.Exif)
    if dt:
        ifd[0x9003] = dt
    if offset:
        ifd[0x9011] = offset
    ifd[0x8827] = 200
    if gps:
        def dms(v):
            v = abs(v)
            d = int(v); m = int((v - d) * 60); s = round(((v - d) * 60 - m) * 60, 4)
            return (float(d), float(m), float(s))
        g = exif.get_ifd(ExifTags.IFD.GPSInfo)
        g[1] = "N" if gps[0] >= 0 else "S"
        g[2] = dms(gps[0])
        g[3] = "E" if gps[1] >= 0 else "W"
        g[4] = dms(gps[1])
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def png_bytes(size=(32, 32)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", size, (0, 0, 255, 128)).save(buf, format="PNG")
    return buf.getvalue()


def create_place(client, name="서울", lat=37.5665, lon=126.9780, cc="KR") -> str:
    r = client.post("/api/v1/places", json={"name": name, "latitude": lat, "longitude": lon, "country_code": cc})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def upload(client, place_id: str, visibility="PRIVATE", data: bytes | None = None, filename="a.jpg", **form) -> "object":
    files = {"file": (filename, data if data is not None else jpeg_bytes(), "image/jpeg")}
    payload = {"place_id": place_id, "visibility": visibility, **{k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in form.items()}}
    return client.post("/api/v1/photos", files=files, data=payload)


def befriend(a: UserClient, b: UserClient) -> str:
    r = a.post("/api/v1/friends/requests", json={"target_user_id": b.id})
    assert r.status_code == 201, r.text
    fid = r.json()["id"]
    r = b.post(f"/api/v1/friends/{fid}/accept")
    assert r.status_code == 200, r.text
    return fid


def rand_uuid() -> str:
    return str(uuid.uuid4())
