from app.core.config import BACKEND_DIR, Settings
from app.core.errors import not_found

API = "/api/v1"


def test_env_file_is_backend_relative():
    # 실행 위치(cwd)가 달라도 backend 폴더의 .env를 읽는다
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
