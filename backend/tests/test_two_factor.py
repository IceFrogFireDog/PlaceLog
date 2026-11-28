"""2단계 인증 (TOTP + 복구 코드)."""
import base64
import uuid

from app.core import totp
from app.core.database import SessionLocal
from app.models import RecoveryCode, User
from app.tasks import main as tasks_main
from tests.conftest import PASSWORD, UserClient, make_client

API = "/api/v1"


def secret_of(b32: str) -> bytes:
    return base64.b32decode(b32 + "=" * (-len(b32) % 8))


def code(secret: bytes, offset: int = 0) -> str:
    return totp.code_at(secret, totp.current_step() + offset)


def login(c, email, pw=PASSWORD, otp=None):
    body = {"email": email, "password": pw}
    if otp is not None:
        body["otp"] = otp
    return c.post(f"{API}/auth/login", json=body)


def turn_on(u: UserClient) -> tuple[bytes, list[str]]:
    r = u.post(f"{API}/auth/2fa/setup", json={"password": PASSWORD})
    assert r.status_code == 200, r.text
    assert r.json()["otpauth_uri"].startswith("otpauth://totp/") and f"secret={r.json()['secret']}" in r.json()["otpauth_uri"]
    secret = secret_of(r.json()["secret"])
    r = u.post(f"{API}/auth/2fa/enable", json={"code": code(secret)})
    assert r.status_code == 200, r.text
    return secret, r.json()["recovery_codes"]


def test_rfc6238_reference_vector():
    # RFC 6238 부록 B (SHA-1, 시각 59초 → 94287082의 뒤 6자리)
    secret = b"12345678901234567890"
    assert totp.code_at(secret, 59 // 30) == "287082"
    assert totp.match_step(secret, "287082", now=59) == 1
    assert totp.match_step(secret, "287 082", now=59 + 30) == 1  # 30초 오차 허용, 공백 무시
    assert totp.match_step(secret, "287082", now=59 + 90) is None


def test_setup_enable_and_login_flow():
    u = UserClient("otpuser")
    assert u.post(f"{API}/auth/2fa/setup", json={"password": "wrong-password-1"}).status_code == 422
    r = u.post(f"{API}/auth/2fa/setup", json={"password": PASSWORD})
    secret = secret_of(r.json()["secret"])
    assert u.post(f"{API}/auth/2fa/enable", json={"code": "000000" if code(secret) != "000000" else "111111"}).status_code == 422
    assert u.get(f"{API}/auth/me").json()["two_factor_enabled"] is False  # 코드 확인 전에는 꺼진 상태
    codes = u.post(f"{API}/auth/2fa/enable", json={"code": code(secret)}).json()["recovery_codes"]
    assert len(codes) == 10 and len(set(codes)) == 10
    assert u.get(f"{API}/auth/me").json()["two_factor_enabled"] is True
    assert u.get(f"{API}/auth/2fa").json() == {"enabled": True, "recovery_codes_left": 10}

    c = make_client()
    r = login(c, u.email)
    assert r.status_code == 401 and r.json()["code"] == "OTP_REQUIRED"
    assert c.get(f"{API}/auth/me").status_code == 401  # 비밀번호만으로는 세션이 생기지 않음
    assert login(c, "otpuser@example.com", "wrong-password-1", otp=code(secret, 1)).json()["code"] == "INVALID_CREDENTIALS"
    r = login(c, u.email, otp="123456" if code(secret, 1) != "123456" else "654321")
    assert r.status_code == 401 and r.json()["code"] == "OTP_INVALID"
    next_code = code(secret, 1)  # 설정 때 쓴 현재 코드는 재사용 불가 → 다음 30초 코드
    assert login(c, u.email, otp=next_code).status_code == 200
    assert login(make_client(), u.email, otp=next_code).json()["code"] == "OTP_INVALID"  # 같은 코드 재사용 막음

    # 복구 코드: 한 번만
    d = make_client()
    assert login(d, u.email, otp=codes[0].upper()).status_code == 200
    assert login(make_client(), u.email, otp=codes[0]).status_code == 401
    assert d.get(f"{API}/auth/2fa").json()["recovery_codes_left"] == 9


def test_secret_not_stored_and_recovery_codes_hashed():
    u = UserClient("storage2fa")
    secret, codes = turn_on(u)
    with SessionLocal() as db:
        user = db.get(User, uuid.UUID(u.id))
        assert user.totp_salt and totp.b32(secret) not in (user.totp_salt or "")
        hashes = [rc.code_hash for rc in db.query(RecoveryCode).filter(RecoveryCode.user_id == user.id)]
        assert len(hashes) == 10 and not any(c.replace("-", "") in h for c in codes for h in hashes)


def test_otp_attempts_limited_per_account():
    u = UserClient("bruteforce")
    secret, _ = turn_on(u)
    wrong = "000000" if code(secret, 1) != "000000" else "111111"
    asks = [login(make_client(), u.email).json()["code"] for _ in range(2)]
    assert asks == ["OTP_REQUIRED"] * 2  # 코드를 묻는 단계는 세지 않음 (로그인 자체 한도는 IP+이메일당 분당 10회)
    statuses = [login(make_client(), u.email, otp=wrong).status_code for _ in range(6)]
    assert statuses[:5] == [401] * 5 and statuses[5] == 429  # 틀린 코드 5번이면 잠김
    assert login(make_client(), u.email, otp=code(secret, 1)).status_code == 429  # 잠긴 동안은 맞는 코드도 거절


def test_disable_and_regenerate_codes():
    u = UserClient("toggle2fa")
    secret, codes = turn_on(u)
    r = u.post(f"{API}/auth/2fa/recovery-codes", json={"password": PASSWORD, "code": codes[0]})
    assert r.status_code == 200
    fresh = r.json()["recovery_codes"]
    assert login(make_client(), u.email, otp=codes[1]).status_code == 401  # 이전 코드는 모두 무효
    assert u.post(f"{API}/auth/2fa/disable", json={"password": "wrong-password-1", "code": fresh[0]}).status_code == 422
    assert u.post(f"{API}/auth/2fa/disable", json={"password": PASSWORD, "code": "999999"}).status_code == 422
    assert u.post(f"{API}/auth/2fa/disable", json={"password": PASSWORD, "code": fresh[0]}).status_code == 200
    assert u.get(f"{API}/auth/me").json()["two_factor_enabled"] is False
    assert login(make_client(), u.email).status_code == 200  # 다시 비밀번호만으로 로그인
    with SessionLocal() as db:
        assert db.query(RecoveryCode).filter(RecoveryCode.user_id == uuid.UUID(u.id)).count() == 0


def test_operator_can_reset_and_account_delete_removes_codes(capsys):
    u = UserClient("lostphone")
    turn_on(u)
    assert tasks_main(["disable-2fa", "LOSTPHONE@example.com"]) == 0
    assert "해제" in capsys.readouterr().out
    assert login(make_client(), u.email).status_code == 200
    assert tasks_main(["disable-2fa", "nobody@example.com"]) == 1

    v = UserClient("leaver2fa")
    turn_on(v)
    assert v.request("DELETE", f"{API}/users/me", json={"password": PASSWORD}).status_code == 204
    with SessionLocal() as db:
        assert db.query(RecoveryCode).filter(RecoveryCode.user_id == uuid.UUID(v.id)).count() == 0
