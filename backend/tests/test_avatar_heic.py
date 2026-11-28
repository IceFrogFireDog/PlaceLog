"""HEIC(아이폰) 업로드와 프로필 사진."""
import io
from pathlib import Path

from PIL import Image

from app.services.storage_service import get_storage
from tests.conftest import befriend, create_place, jpeg_bytes, png_bytes, upload

API = "/api/v1"
HEIC = (Path(__file__).parent / "fixtures" / "iphone_gps.heic").read_bytes()


def test_heic_upload_reads_exif_and_converts(users):
    a, b, _ = users
    pid = create_place(a)
    r = upload(a, pid, "PUBLIC", data=HEIC, filename="IMG_0001.HEIC")
    assert r.status_code == 201, r.text
    p = r.json()
    assert (p["width"], p["height"]) == (240, 320)  # HEIF 회전 정보가 적용된 세로 사진
    assert abs(p["shot_latitude"] - 37.5796) < 1e-3 and abs(p["shot_longitude"] - 126.977) < 1e-3
    assert p["taken_timezone"] == "+09:00" and p["taken_at"].startswith("2026-05-02T06:20:00")  # 15:20 KST
    assert p["camera"] == "Apple iPhone 15 Pro"

    disp = a.get(f"{API}/media/{p['id']}/display")
    assert disp.headers["content-type"] == "image/webp"
    im = Image.open(io.BytesIO(disp.content))
    assert im.size == (240, 320) and not im.getexif()  # 위치정보 제거
    orig = a.get(f"{API}/media/{p['id']}/original")
    assert orig.status_code == 200 and orig.headers["content-type"] == "image/heic" and orig.content == HEIC
    assert b.get(f"{API}/media/{p['id']}/original").status_code == 404  # 원본은 작성자만
    assert b.get(f"{API}/photos/{p['id']}").json()["shot_latitude"] is None  # 정확 좌표 비공개 기본값


def test_truncated_heic_rejected(users):
    a, *_ = users
    pid = create_place(a)
    assert upload(a, pid, data=HEIC[: len(HEIC) // 2], filename="broken.heic").status_code == 415  # 헤더 검사에서 바로 거절


def test_truncated_jpeg_fails_processing(users):
    """헤더는 멀쩡하고 이미지 데이터가 잘린 파일: 등록은 되지만 변환이 실패해 작성자에게만 '변환 실패'로 보인다."""
    a, b, _ = users
    pid = create_place(a)
    upload(a, pid, "PUBLIC")
    data = jpeg_bytes(size=(800, 600))
    r = upload(a, pid, "PUBLIC", data=data[: len(data) // 2])
    assert r.status_code == 201
    d = a.get(f"{API}/photos/{r.json()['id']}").json()
    assert d["status"] == "FAILED" and "읽을 수 없습니다" in d["processing_error"]
    assert b.get(f"{API}/photos/{r.json()['id']}").status_code == 404
    assert b.get(f"{API}/places/{pid}").json()["photo_count"] == 1


def test_avatar_lifecycle(users, anon):
    a, b, _ = users
    r = a.put(f"{API}/users/me/avatar", files={"file": ("me.jpg", jpeg_bytes(size=(300, 200), gps=(37.5, 127.0)), "image/jpeg")})
    assert r.status_code == 200, r.text
    url = r.json()["avatar_url"]
    assert url.startswith(f"/api/v1/media/avatars/{a.id}/")

    img = anon.get(url)
    assert img.status_code == 200 and img.headers["content-type"] == "image/webp" and "public" in img.headers["cache-control"]
    im = Image.open(io.BytesIO(img.content))
    assert im.size == (256, 256) and not im.getexif()  # 정사각형, 위치정보 제거

    assert anon.get(f"{API}/users/alice").json()["avatar_url"] == url
    assert a.get(f"{API}/auth/me").json()["avatar_url"] == url
    assert b.get(f"{API}/users/search?q=ali").json()["items"][0]["avatar_url"] == url

    r2 = a.put(f"{API}/users/me/avatar", files={"file": ("me2.png", png_bytes((64, 64)), "image/png")})
    url2 = r2.json()["avatar_url"]
    assert url2 != url and anon.get(url).status_code == 404  # 옛 주소는 사라짐
    assert len(list(get_storage().list_keys(f"avatars/{a.id}/"))) == 1  # 옛 파일 삭제

    assert a.put(f"{API}/users/me/avatar", files={"file": ("me.heic", HEIC, "image/heic")}).status_code == 200

    assert a.delete(f"{API}/users/me/avatar").status_code == 204
    assert anon.get(f"{API}/users/alice").json()["avatar_url"] is None
    assert list(get_storage().list_keys(f"avatars/{a.id}/")) == []


def test_avatar_rejections(users, anon):
    a, b, _ = users
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, "GIF")
    assert a.put(f"{API}/users/me/avatar", files={"file": ("x.gif", gif.getvalue(), "image/gif")}).status_code == 415
    assert anon.put(f"{API}/users/me/avatar", files={"file": ("x.jpg", jpeg_bytes(), "image/jpeg")}).status_code == 401
    url = a.put(f"{API}/users/me/avatar", files={"file": ("x.jpg", jpeg_bytes(), "image/jpeg")}).json()["avatar_url"]
    file_id = url.rsplit("/", 1)[-1]
    assert anon.get(f"{API}/media/avatars/{b.id}/{file_id}").status_code == 404  # 다른 사용자 경로로는 못 엶
    assert anon.get(f"{API}/media/avatars/{a.id}/..%2F..%2Fsecret").status_code == 404


def test_avatar_appears_on_photos_and_friend_lists(users):
    a, b, _ = users
    url = a.put(f"{API}/users/me/avatar", files={"file": ("x.jpg", jpeg_bytes(), "image/jpeg")}).json()["avatar_url"]
    befriend(a, b)
    pid = create_place(a)
    phid = upload(a, pid, "FRIENDS").json()["id"]
    assert b.get(f"{API}/photos/{phid}").json()["owner"]["avatar_url"] == url
    assert b.get(f"{API}/friends").json()["items"][0]["user"]["avatar_url"] == url
