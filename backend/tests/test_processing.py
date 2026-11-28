"""사진 변환 작업 큐 (PROCESSING → READY / FAILED)."""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import update

from app.core.database import SessionLocal, utcnow
from app.models import Photo
from app.services import image_service, processing_service
from app.services.storage_service import get_storage
from app.tasks import main as tasks_main
from tests.conftest import befriend, create_place, upload

API = "/api/v1"


@pytest.fixture
def no_background(monkeypatch):
    """응답 뒤 바로 변환하지 않게 해서 PROCESSING 상태를 관찰한다 (서버가 꺼진 상황과 같음)."""

    async def skip(pid):
        return None

    monkeypatch.setattr(processing_service, "run_job", skip)


def _set(pid: str, **values):
    with SessionLocal() as db:
        db.execute(update(Photo).where(Photo.id == uuid.UUID(pid)).values(**values))
        db.commit()


def test_upload_returns_processing_then_ready(users):
    a, *_ = users
    pid = create_place(a)
    r = upload(a, pid, "PUBLIC")
    assert r.status_code == 201 and r.json()["status"] == "PROCESSING"  # 원본만 저장하고 바로 응답
    phid = r.json()["id"]
    d = a.get(f"{API}/photos/{phid}").json()  # 응답 직후 백그라운드 변환 완료
    assert d["status"] == "READY" and d["processing_error"] is None
    assert a.get(f"{API}/media/{phid}/display").headers["content-type"] == "image/webp"


def test_processing_photo_visible_only_to_owner(users, anon, no_background):
    a, b, _ = users
    befriend(a, b)
    pid = create_place(a, "새 장소", 36.0, 128.0)
    phid = upload(a, pid, "PUBLIC").json()["id"]

    mine = a.get(f"{API}/users/alice/photos").json()["items"]
    assert [p["status"] for p in mine] == ["PROCESSING"]
    assert a.get(f"{API}/media/{phid}/thumbnail").json()["code"] == "PHOTO_PROCESSING"
    assert a.get(f"{API}/media/{phid}/original").status_code == 200  # 원본은 바로 받을 수 있음

    for viewer in (anon, b):
        assert viewer.get(f"{API}/photos/{phid}").status_code == 404
        assert viewer.get(f"{API}/media/{phid}/thumbnail").status_code == 404
        assert viewer.get(f"{API}/users/alice/photos").json()["items"] == []
        assert viewer.get(f"{API}/places/{pid}").status_code == 404  # 보이는 사진이 없는 남의 장소
    assert anon.get(f"{API}/map/places", params={"mode": "WORLD", "zoom": 10}).json()["items"] == []
    assert a.get(f"{API}/map/places", params={"mode": "ME", "zoom": 10}).json()["items"] == []  # 지구본은 변환이 끝난 사진만

    assert processing_service.process_photo(uuid.UUID(phid)) == "READY"
    assert anon.get(f"{API}/photos/{phid}").status_code == 200
    assert anon.get(f"{API}/map/places", params={"mode": "WORLD", "zoom": 10}).json()["items"][0]["photo_count"] == 1


def test_worker_picks_up_unstarted_and_stale_jobs(users, no_background, capsys):
    a, *_ = users
    pid = create_place(a)
    fresh = upload(a, pid).json()["id"]
    unstarted = upload(a, pid).json()["id"]
    stale = upload(a, pid).json()["id"]
    long_ago = utcnow() - timedelta(hours=1)
    _set(unstarted, created_at=long_ago)  # 업로드 후 서버가 꺼져 시작도 못 한 작업
    _set(stale, created_at=long_ago, processing_started_at=long_ago, processing_attempts=1)  # 변환 중 멈춘 작업

    assert tasks_main(["process-pending"]) == 0
    assert "READY=2" in capsys.readouterr().out
    statuses = {i: a.get(f"{API}/photos/{i}").json()["status"] for i in (fresh, unstarted, stale)}
    assert statuses == {fresh: "PROCESSING", unstarted: "READY", stale: "READY"}  # 막 올린 것은 백그라운드 작업 몫


def test_claim_prevents_double_processing(users, no_background):
    a, *_ = users
    phid = uuid.UUID(upload(a, create_place(a)).json()["id"])
    _set(str(phid), processing_started_at=utcnow())  # 다른 곳에서 처리 중
    assert processing_service.process_photo(phid) is None
    with SessionLocal() as db:  # 세션을 닫지 않으면 PostgreSQL에서 다음 테스트의 테이블 삭제가 잠금에 걸린다
        assert processing_service.pending_ids(db) == []


def test_gives_up_after_max_attempts(users, no_background):
    a, *_ = users
    phid = upload(a, create_place(a)).json()["id"]
    long_ago = utcnow() - timedelta(hours=1)
    _set(phid, created_at=long_ago, processing_started_at=long_ago, processing_attempts=processing_service.MAX_ATTEMPTS)
    processing_service.process_pending()
    d = a.get(f"{API}/photos/{phid}").json()
    assert d["status"] == "FAILED" and "여러 번" in d["processing_error"]


def test_deleted_while_processing_leaves_no_files(users, no_background, monkeypatch):
    a, *_ = users
    phid = upload(a, create_place(a)).json()["id"]
    real = image_service.process

    def delete_midway(data):
        out = real(data)
        assert a.delete(f"{API}/photos/{phid}").status_code == 204  # 변환하는 사이에 작성자가 삭제
        return out

    monkeypatch.setattr(image_service, "process", delete_midway)
    assert processing_service.process_photo(uuid.UUID(phid)) is None
    assert list(get_storage().list_keys(f"photos/{a.id}/{phid}/")) == []


def test_retry_requires_owner(users):
    a, b, _ = users
    pid = create_place(a)
    phid = upload(a, pid, "PUBLIC").json()["id"]
    _set(phid, status="FAILED", processing_error="x")
    assert b.post(f"{API}/photos/{phid}/retry").status_code == 404  # 남에게는 실패한 사진이 보이지 않음
    assert a.post(f"{API}/photos/{phid}/retry").json()["status"] == "PROCESSING"
    assert a.get(f"{API}/photos/{phid}").json()["status"] == "READY"
