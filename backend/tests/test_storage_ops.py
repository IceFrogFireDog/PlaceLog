"""S3 호환 저장소, 정리 작업(CLI), 장소 병합, Redis 빈도 제한."""
import os
import uuid
from datetime import timedelta

import boto3
import fakeredis
import pytest
from moto import mock_aws

from app.core.database import SessionLocal, utcnow
from app.core.errors import AppError
from app.core.ratelimit import RedisRateLimiter
from app.models import EmailToken, Photo, Place, UserSession
from app.services.storage_service import S3Storage, get_storage, set_storage
from app.tasks import main as tasks_main
from tests.conftest import create_place, jpeg_bytes, upload

API = "/api/v1"


@pytest.fixture
def s3():
    for k, v in {"AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing", "AWS_DEFAULT_REGION": "us-east-1"}.items():
        os.environ[k] = v
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="photos-test")
        old = get_storage()
        st = S3Storage("photos-test", prefix="pg", client=client)
        set_storage(st)
        try:
            yield st, client
        finally:
            set_storage(old)


def _keys(client) -> list[str]:
    return [o["Key"] for o in client.list_objects_v2(Bucket="photos-test").get("Contents", [])]


def test_s3_upload_serve_delete(users, s3):
    st, client = s3
    a, b, _ = users
    pid = create_place(a)
    phid = upload(a, pid, "FRIENDS").json()["id"]
    keys = _keys(client)
    assert len(keys) == 3 and all(k.startswith(f"pg/photos/{a.id}/{phid}/") for k in keys)
    grants = client.get_object_acl(Bucket="photos-test", Key=keys[0])["Grants"]
    assert all("AllUsers" not in str(g) for g in grants)  # 버킷 객체는 비공개
    assert client.head_object(Bucket="photos-test", Key=f"pg/photos/{a.id}/{phid}/thumb.webp")["ContentType"] == "image/webp"

    thumb = a.get(f"{API}/media/{phid}/thumbnail")
    assert thumb.status_code == 200 and thumb.content[:4] == b"RIFF"  # 권한 확인 후 백엔드가 전달
    assert b.get(f"{API}/media/{phid}/thumbnail").status_code == 404

    a.put(f"{API}/users/me/avatar", files={"file": ("x.jpg", jpeg_bytes(), "image/jpeg")})
    assert any(k.startswith(f"pg/avatars/{a.id}/") for k in _keys(client))

    assert a.delete(f"{API}/photos/{phid}").status_code == 204
    assert not any(k.startswith("pg/photos/") for k in _keys(client))


def test_cleanup_on_s3(users, s3):
    st, client = s3
    a, *_ = users
    pid = create_place(a)
    phid = upload(a, pid).json()["id"]
    st.save(f"photos/{a.id}/{uuid.uuid4()}/display.webp", b"orphan")
    st.save(f"avatars/{a.id}/deadbeef.webp", b"old avatar")
    assert tasks_main(["cleanup", "--min-age", "0"]) == 0
    keys = _keys(client)
    assert len([k for k in keys if "/photos/" in k]) == 3 and all(phid in k for k in keys if "/photos/" in k)
    assert not any("deadbeef" in k for k in keys)


def test_cleanup_local_files_sessions_tokens(users, capsys):
    a, *_ = users
    st = get_storage()
    pid = create_place(a)
    phid = upload(a, pid).json()["id"]
    orphan = f"photos/{a.id}/{uuid.uuid4()}/thumb.webp"
    st.save(orphan, b"x")
    with SessionLocal() as db:
        sess = db.query(UserSession).first()
        db.add(UserSession(user_id=sess.user_id, token_hash="e" * 64, csrf_token_hash="e" * 64, expires_at=utcnow() - timedelta(seconds=1)))
        db.add(EmailToken(user_id=sess.user_id, purpose="RESET", token_hash="f" * 64, expires_at=utcnow() - timedelta(seconds=1)))
        db.commit()

    assert tasks_main(["cleanup", "--min-age", "3600"]) == 0  # 방금 만든 파일은 업로드 중일 수 있어 보호
    assert st.path_for(orphan) is not None
    assert tasks_main(["cleanup", "--min-age", "0"]) == 0
    first, second = capsys.readouterr().out.strip().splitlines()
    assert "photo_files=0," in first and "sessions=1," in first and "tokens=1" in first  # 세션·토큰은 바로, 파일은 1시간 지난 것만
    assert "photo_files=1," in second
    assert st.path_for(orphan) is None and st.path_for(f"photos/{a.id}/{phid}/thumb.webp") is not None
    assert a.get(f"{API}/auth/me").status_code == 200  # 유효한 세션은 그대로


def test_duplicates_and_merge_cli(users, capsys):
    a, *_ = users
    p1 = create_place(a, "남산타워", 37.5512, 126.9882)
    r = a.post(f"{API}/places", json={"name": "남산 타워", "latitude": 37.5513, "longitude": 126.9883, "force": True})
    p2 = r.json()["id"]
    upload(a, p1, "PUBLIC")
    upload(a, p2, "PUBLIC")
    upload(a, p2, "PUBLIC")
    tasks_main(["duplicates"])
    out = capsys.readouterr().out
    assert "중복 후보 1쌍" in out and p1 in out and p2 in out
    assert tasks_main(["merge-places", p2, p1]) == 0
    assert "사진 2장" in capsys.readouterr().out
    with SessionLocal() as db:
        assert db.get(Place, uuid.UUID(p2)) is None
        assert db.query(Photo).filter(Photo.place_id == uuid.UUID(p1)).count() == 3
    assert tasks_main(["merge-places", p1, p1]) == 1


def test_redis_rate_limiter_shared_between_servers():
    shared = fakeredis.FakeRedis()
    server1 = RedisRateLimiter("login", 2, 60, client=shared)
    server2 = RedisRateLimiter("login", 2, 60, client=shared)
    server1.hit("1.2.3.4")
    server2.hit("1.2.3.4")
    with pytest.raises(AppError) as e:
        server1.hit("1.2.3.4")
    assert e.value.status == 429
    server1.hit("5.6.7.8")  # 다른 키는 별도


def test_redis_down_fails_open():
    class Broken:
        def pipeline(self):
            raise ConnectionError("redis down")

    lim = RedisRateLimiter("x", 1, 60, client=Broken())
    lim.hit("k")
    lim.hit("k")  # 예외 없이 통과 (서비스 중단 방지)
