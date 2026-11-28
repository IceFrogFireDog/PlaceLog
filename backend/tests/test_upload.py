import io
from datetime import datetime

from PIL import Image

from app.services import storage_service
from tests.conftest import create_place, jpeg_bytes, png_bytes, upload

API = "/api/v1"


def test_upload_private_default_with_exif(users):
    a, b, _ = users
    pid = create_place(a)
    data = jpeg_bytes(gps=(37.5665, 126.978), dt="2026:05:01 14:30:00", offset="+09:00")
    files = {"file": ("x.jpg", data, "image/jpeg")}
    r = a.post(f"{API}/photos", files=files, data={"place_id": pid})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["visibility"] == "PRIVATE"
    assert abs(p["shot_latitude"] - 37.5665) < 1e-3 and abs(p["shot_longitude"] - 126.978) < 1e-3
    assert datetime.fromisoformat(p["taken_at"]).hour == 5  # 14:30 KST → 05:30 UTC
    assert p["taken_timezone"] == "+09:00" and p["camera"] == "TestMake TestCam 1" and p["iso"] == 200
    assert b.get(f"{API}/photos/{p['id']}").status_code == 404

    # 표시용·썸네일에는 EXIF(GPS) 없음
    disp = a.get(f"{API}/media/{p['id']}/display")
    assert disp.headers["content-type"] == "image/webp"
    assert not Image.open(io.BytesIO(disp.content)).getexif()


def test_exif_time_without_offset_not_guessed(users):
    a, *_ = users
    pid = create_place(a)
    r = upload(a, pid, data=jpeg_bytes(dt="2026:05:01 14:30:00"))
    assert r.status_code == 201 and r.json()["taken_at"] is None


def test_no_gps_manual_location(users):
    a, *_ = users
    pid = create_place(a, "교토", 35.0116, 135.7681, "JP")
    r = upload(a, pid, data=jpeg_bytes(), shot_latitude=35.0, shot_longitude=135.7)
    assert r.status_code == 201
    assert r.json()["place"]["name"] == "교토" and r.json()["shot_latitude"] == 35.0


def test_png_and_orientation(users):
    a, *_ = users
    pid = create_place(a)
    assert upload(a, pid, data=png_bytes(), filename="a.png").status_code == 201
    r = upload(a, pid, data=jpeg_bytes(size=(60, 30), orientation=6))
    assert (r.json()["width"], r.json()["height"]) == (30, 60)


def test_fake_extension_rejected(users):
    a, *_ = users
    pid = create_place(a)
    r = upload(a, pid, data=b"GIF89a not really an image" * 10, filename="evil.jpg")
    assert r.status_code == 415
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, format="GIF")
    assert upload(a, pid, data=gif.getvalue(), filename="x.jpg").status_code == 415


def test_too_large(users):
    a, *_ = users
    pid = create_place(a)
    assert upload(a, pid, data=b"\xff" * (2 * 1024 * 1024 + 10)).status_code == 413
    assert upload(a, pid, data=jpeg_bytes(size=(2100, 2000))).status_code == 413  # 4MP 초과


def test_corrupt_exif_allowed(users):
    a, *_ = users
    pid = create_place(a)
    data = bytearray(jpeg_bytes(gps=(10, 10)))
    i = data.find(b"Exif\x00\x00")
    data[i + 20 : i + 60] = b"\x00\xff" * 20  # EXIF 일부 손상
    r = upload(a, pid, data=bytes(data))
    assert r.status_code == 201  # 손상 EXIF는 무시하고 등록
    assert r.json()["visibility"] == "PRIVATE"


def test_corrupt_orientation_tag_allowed(users):
    a, *_ = users
    pid = create_place(a)
    assert upload(a, pid, data=jpeg_bytes(orientation=99)).status_code == 201


def test_content_length_precheck(users):
    a, *_ = users
    r = a.post("/api/v1/photos", content=b"x" * 10, headers={"Content-Length": str(50 * 1024 * 1024), "Content-Type": "multipart/form-data; boundary=zz"})
    assert r.status_code == 413 and r.json()["code"] == "FILE_TOO_LARGE"


def test_large_jpeg_dimensions_preserved(users):
    a, *_ = users
    pid = create_place(a)
    r = upload(a, pid, data=jpeg_bytes(size=(2000, 1000)))  # draft 축소 디코딩 후에도 원본 크기 기록
    assert (r.json()["width"], r.json()["height"]) == (2000, 1000)
    disp = Image.open(io.BytesIO(a.get(f"{API}/media/{r.json()['id']}/display").content))
    assert disp.size == (2000, 1000)  # 2400 이하라 확대·축소 없음


def test_bad_inputs(users, anon):
    a, *_ = users
    pid = create_place(a)
    assert upload(anon, pid).status_code == 401
    assert upload(a, "not-a-uuid").status_code == 422
    assert upload(a, pid, shot_latitude=10).status_code == 422
    assert upload(a, pid, shot_latitude=100, shot_longitude=0).status_code == 422


def test_storage_failure_cleanup(users, monkeypatch):
    """업로드 때 원본 저장이 실패하면 500, 남는 파일·사진 없음."""
    a, *_ = users
    pid = create_place(a)
    st = storage_service.get_storage()
    calls = []

    def broken(key, data):
        calls.append(key)
        raise OSError("disk full")

    monkeypatch.setattr(st, "save", broken)
    r = upload(a, pid)
    assert r.status_code == 500 and r.json()["code"] == "STORAGE_ERROR"
    assert calls and all(st.path_for(k) is None for k in calls)
    assert a.get(f"{API}/users/alice").json()["photo_count"] == 0


def test_storage_failure_during_processing_marks_failed_then_retry(users, monkeypatch):
    """변환 중 저장 실패 → FAILED(만들던 파일 정리, 원본은 유지) → 다시 시도하면 READY."""
    a, *_ = users
    pid = create_place(a)
    st = storage_service.get_storage()
    real_save, calls = st.save, []

    def flaky(key, data):
        calls.append(key)
        if key.endswith("thumb.webp"):
            raise OSError("disk full")
        real_save(key, data)

    monkeypatch.setattr(st, "save", flaky)
    r = upload(a, pid)
    assert r.status_code == 201
    phid = r.json()["id"]
    d = a.get(f"{API}/photos/{phid}").json()
    assert d["status"] == "FAILED" and "다시 시도" in d["processing_error"]
    original = next(k for k in calls if "original" in k)
    assert st.path_for(original) is not None  # 원본은 남김 (다시 시도용)
    assert all(st.path_for(k) is None for k in calls if "original" not in k)  # 만들던 파일은 정리
    assert a.get(f"{API}/media/{phid}/thumbnail").json()["code"] == "PHOTO_FAILED"

    monkeypatch.setattr(st, "save", real_save)
    assert a.post(f"{API}/photos/{phid}/retry").status_code == 200
    assert a.get(f"{API}/photos/{phid}").json()["status"] == "READY"
    assert a.get(f"{API}/media/{phid}/thumbnail").status_code == 200
    assert a.post(f"{API}/photos/{phid}/retry").status_code == 409  # 실패한 사진만


def test_db_failure_cleanup(users, monkeypatch):
    a, *_ = users
    pid = create_place(a)
    from sqlalchemy.orm import Session

    saved = []
    st = storage_service.get_storage()
    real_save = st.save
    monkeypatch.setattr(st, "save", lambda k, d: (saved.append(k), real_save(k, d)))
    real_commit = Session.commit

    def boom(self):
        if any(isinstance(o, __import__("app.models", fromlist=["Photo"]).Photo) for o in self.new):
            raise RuntimeError("db down")
        return real_commit(self)

    monkeypatch.setattr(Session, "commit", boom)
    import pytest

    with pytest.raises(RuntimeError):  # TestClient는 서버 예외를 그대로 올림 (실서버는 500 INTERNAL_ERROR)
        upload(a, pid)
    assert saved and all(st.path_for(k) is None for k in saved)


def test_use_exif_date_false_keeps_date_empty(users):
    """사용자가 촬영일을 일부러 비우면 EXIF 날짜로 다시 채우지 않는다 (기본값은 EXIF 사용)."""
    a, *_ = users
    pid = create_place(a)
    data = jpeg_bytes(dt="2024:03:01 10:00:00", offset="+09:00")
    assert upload(a, pid, data=data).json()["taken_at"].startswith("2024-03-01T01:00:00")
    r = upload(a, pid, data=data, use_exif_date=False)
    assert r.status_code == 201 and r.json()["taken_at"] is None and r.json()["taken_timezone"] is None
