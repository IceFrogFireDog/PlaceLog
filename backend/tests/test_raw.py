"""카메라 RAW(DNG 등) 업로드. 고정 파일은 tests/fixtures/make_raw.py로 만든 DNG."""
import io
from pathlib import Path

from PIL import Image

from app.core.config import settings
from tests.conftest import create_place, jpeg_bytes, upload

API = "/api/v1"
FIX = Path(__file__).parent / "fixtures"
RAW_GPS = (FIX / "raw_gps.dng").read_bytes()  # 600x400 센서, 방향 6, EXIF 촬영일(+09:00)·GPS
RAW_PREVIEW = (FIX / "raw_preview.dng").read_bytes()  # 1800x1200 초록색 JPEG 미리보기 포함


def test_dng_upload_reads_exif_rotates_and_converts(users):
    a, b, _ = users
    pid = create_place(a)
    r = upload(a, pid, "PUBLIC", data=RAW_GPS, filename="DSC_0001.DNG")
    assert r.status_code == 201, r.text
    assert (r.json()["width"], r.json()["height"]) == (400, 600)  # 세로 사진 (방향 보정)
    phid = r.json()["id"]
    d = a.get(f"{API}/photos/{phid}").json()
    assert d["status"] == "READY"
    assert abs(d["shot_latitude"] - 37.5445) < 1e-4 and abs(d["shot_longitude"] - 127.0374) < 1e-4
    assert d["taken_timezone"] == "+09:00" and d["taken_at"].startswith("2025-08-15T00:30:00")
    assert d["camera"] == "PhotoGlobe Test DNG"

    disp = a.get(f"{API}/media/{phid}/display")
    assert disp.headers["content-type"] == "image/webp"
    im = Image.open(io.BytesIO(disp.content))
    assert im.width < im.height and not im.getexif()  # 세로, 위치정보 제거
    orig = a.get(f"{API}/media/{phid}/original")
    assert orig.headers["content-type"] == "image/x-adobe-dng" and orig.content == RAW_GPS
    assert b.get(f"{API}/media/{phid}/original").status_code == 404  # 원본은 작성자만
    assert b.get(f"{API}/photos/{phid}").json()["shot_latitude"] is None


def test_dng_uses_embedded_preview(users):
    a, *_ = users
    phid = upload(a, create_place(a), data=RAW_PREVIEW, filename="preview.dng").json()["id"]
    im = Image.open(io.BytesIO(a.get(f"{API}/media/{phid}/display").content)).convert("RGB")
    assert im.size == (1800, 1200)  # 현상하지 않고 카메라 미리보기 사용
    r, g, b = im.getpixel((900, 600))
    assert g > 150 and r < 80 and b < 100


def test_raw_extension_from_filename(users):
    a, *_ = users
    pid = create_place(a)
    named = upload(a, pid, data=RAW_GPS, filename="IMG.NEF").json()["id"]
    unnamed = upload(a, pid, data=RAW_GPS, filename="upload.bin").json()["id"]
    assert a.get(f"{API}/media/{named}/original").headers["content-type"] == "application/octet-stream"
    assert a.get(f"{API}/photos/{unnamed}").json()["status"] == "READY"


def test_raw_limits_and_switch(users, monkeypatch):
    a, *_ = users
    pid = create_place(a)
    # 일반 사진 한도(테스트 2MB)를 넘는 JPEG는 RAW 한도 안이어도 거절
    big = jpeg_bytes(size=(1900, 1900)) + b"\x00" * (2 * 1024 * 1024)
    assert upload(a, pid, data=big).status_code == 413
    monkeypatch.setattr(settings, "max_raw_upload_bytes", 100 * 1024)
    assert upload(a, pid, data=RAW_GPS, filename="a.dng").status_code == 413
    monkeypatch.setattr(settings, "max_raw_upload_bytes", 0)  # RAW 끄기
    r = upload(a, pid, data=RAW_GPS, filename="a.dng")
    assert r.status_code == 415 and "RAW" not in r.json()["message"]


def test_avatar_rejects_raw(users):
    a, *_ = users
    assert a.put(f"{API}/users/me/avatar", files={"file": ("me.dng", RAW_GPS, "image/x-adobe-dng")}).status_code == 415
