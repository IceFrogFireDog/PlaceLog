from pathlib import Path

from app.core.config import BACKEND_DIR, Settings
from app.core.errors import not_found

API = "/api/v1"


def test_relative_storage_path_is_backend_relative(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # 실행 위치가 달라도
    s = Settings(database_url="sqlite://", secret_key="x" * 40, local_storage_path="./storage")
    assert Path(s.local_storage_path) == (BACKEND_DIR / "storage").resolve()
    assert Settings.model_config["env_file"] == BACKEND_DIR / ".env"


def test_korean_particles():
    assert not_found("사용자").message == "사용자를 찾을 수 없습니다."
    assert not_found("사진").message == "사진을 찾을 수 없습니다."
    assert not_found("친구 관계").message == "친구 관계를 찾을 수 없습니다."


def test_blank_display_name_rejected(users):
    a, *_ = users
    r = a.patch(f"{API}/users/me", json={"display_name": "   "})
    assert r.status_code == 422 and "display_name" in r.json()["field_errors"]
    assert a.get(f"{API}/users/alice").json()["display_name"] == "ALICE"
    assert a.get(f"{API}/users/nobody").json()["message"] == "사용자를 찾을 수 없습니다."


def test_security_headers_on_api_and_media(users):
    from tests.conftest import create_place, make_client, upload

    a, *_ = users
    r = make_client().get("/api/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["content-security-policy"].startswith("default-src 'none'")
    pid = create_place(a)
    phid = upload(a, pid, "PUBLIC").json()["id"]
    img = a.get(f"/api/v1/media/{phid}/thumbnail")
    assert img.status_code == 200 and img.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" not in make_client().get("/api/v1/docs").headers  # Swagger 화면은 외부 스크립트 사용
