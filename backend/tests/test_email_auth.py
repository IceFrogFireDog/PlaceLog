"""이메일 인증·비밀번호 재설정·변경·개인정보 동의."""
import logging
from datetime import timedelta

from sqlalchemy import update

from app.core.database import SessionLocal, utcnow
from app.models import EmailToken
from app.services import mail_service
from tests.conftest import PASSWORD, UserClient, last_link, make_client, read_mails, register_payload, upload

API = "/api/v1"


def login(c, email, pw=PASSWORD):
    return c.post(f"{API}/auth/login", json={"email": email, "password": pw})


def test_register_requires_privacy_consent():
    c = make_client()
    r = c.post(f"{API}/auth/register", json=register_payload("noconsent", agree_privacy=False))
    assert r.status_code == 422 and "agree_privacy" in r.json()["field_errors"]
    payload = register_payload("noconsent2")
    del payload["agree_privacy"]
    assert c.post(f"{API}/auth/register", json=payload).status_code == 422


def test_unverified_user_is_limited_until_link_clicked():
    u = UserClient("newbie", verified=False)
    other = UserClient("friendly")
    assert u.get(f"{API}/auth/me").json()["email_verified"] is False

    # 인증 전: 다른 사람에게 영향을 주는 작업은 막힘
    r = u.post(f"{API}/places", json={"name": "카페", "latitude": 37.5, "longitude": 127.0})
    assert r.status_code == 403 and r.json()["code"] == "EMAIL_NOT_VERIFIED"
    assert u.post(f"{API}/friends/requests", json={"target_user_id": other.id}).status_code == 403
    place_id = other.post(f"{API}/places", json={"name": "공원", "latitude": 37.6, "longitude": 127.1}).json()["id"]
    upload(other, place_id, "PUBLIC")
    assert upload(u, place_id, "PUBLIC").status_code == 403
    # 둘러보기·프로필 수정은 가능
    assert u.get(f"{API}/map/places?mode=WORLD").status_code == 200
    assert u.patch(f"{API}/users/me", json={"bio": "안녕"}).status_code == 200

    mails = read_mails(u.email)
    assert len(mails) == 1 and "인증" in mails[0]["Subject"]
    token = last_link(u.email, "/verify-email")
    anon = make_client()  # 메일을 다른 브라우저에서 열어도 된다
    assert anon.post(f"{API}/auth/email/verify", json={"token": token}).status_code == 200
    assert u.get(f"{API}/auth/me").json()["email_verified"] is True
    assert u.post(f"{API}/places", json={"name": "카페", "latitude": 37.5, "longitude": 127.0}).status_code == 201
    # 같은 링크는 한 번만
    assert anon.post(f"{API}/auth/email/verify", json={"token": token}).status_code == 422


def test_resend_invalidates_old_link_and_expiry():
    u = UserClient("late", verified=False)
    first = last_link(u.email, "/verify-email")
    r = u.post(f"{API}/auth/email/resend")
    assert r.status_code == 202
    second = last_link(u.email, "/verify-email")
    assert second != first
    anon = make_client()
    assert anon.post(f"{API}/auth/email/verify", json={"token": first}).status_code == 422  # 이전 링크 무효
    with SessionLocal() as db:
        db.execute(update(EmailToken).values(expires_at=utcnow() - timedelta(seconds=1)))
        db.commit()
    r = anon.post(f"{API}/auth/email/verify", json={"token": second})
    assert r.status_code == 422 and r.json()["code"] == "TOKEN_INVALID"  # 만료
    codes = [u.post(f"{API}/auth/email/resend").status_code for _ in range(3)]
    assert codes == [202, 202, 429]  # 10분에 3회


def test_resend_when_already_verified_sends_nothing():
    u = UserClient("done")
    before = len(read_mails(u.email))
    r = u.post(f"{API}/auth/email/resend")
    assert r.status_code == 202 and "이미" in r.json()["message"]
    assert len(read_mails(u.email)) == before


def test_forgot_and_reset_password():
    u = UserClient("forgetful")
    laptop = make_client()
    assert login(laptop, u.email).status_code == 200
    anon = make_client()
    r1 = anon.post(f"{API}/auth/password/forgot", json={"email": "FORGETFUL@example.com"})
    r2 = anon.post(f"{API}/auth/password/forgot", json={"email": "nobody@example.com"})
    assert r1.status_code == r2.status_code == 202 and r1.json() == r2.json()  # 가입 여부를 드러내지 않음
    assert read_mails("nobody@example.com") == []
    token = last_link(u.email, "/reset-password")

    assert anon.post(f"{API}/auth/password/reset", json={"token": token, "password": "short"}).status_code == 422
    new_pw = "brand-new-password-42"
    assert anon.post(f"{API}/auth/password/reset", json={"token": token, "password": new_pw}).status_code == 200
    assert u.get(f"{API}/auth/me").status_code == 401  # 모든 기기 로그아웃
    assert laptop.get(f"{API}/auth/me").status_code == 401
    assert login(make_client(), u.email).status_code == 401  # 옛 비밀번호
    assert login(make_client(), u.email, new_pw).status_code == 200
    assert anon.post(f"{API}/auth/password/reset", json={"token": token, "password": new_pw + "x"}).status_code == 422  # 1회용


def test_reset_also_verifies_email():
    u = UserClient("unv", verified=False)
    anon = make_client()
    anon.post(f"{API}/auth/password/forgot", json={"email": u.email})
    token = last_link(u.email, "/reset-password")
    assert anon.post(f"{API}/auth/password/reset", json={"token": token, "password": "fresh-password-123"}).status_code == 200
    c = make_client()
    me = login(c, u.email, "fresh-password-123").json()
    assert me["email_verified"] is True


def test_forgot_password_rate_limited_per_email():
    anon = make_client()
    codes = [anon.post(f"{API}/auth/password/forgot", json={"email": "x@example.com"}).status_code for _ in range(4)]
    assert codes == [202, 202, 202, 429]


def test_change_password_keeps_current_session_only():
    u = UserClient("changer")
    phone = make_client()
    login(phone, u.email)
    r = u.post(f"{API}/auth/password/change", json={"current_password": "wrong-password-1", "new_password": "another-password-1"})
    assert r.status_code == 422 and "current_password" in r.json()["field_errors"]
    assert u.post(f"{API}/auth/password/change", json={"current_password": PASSWORD, "new_password": PASSWORD}).status_code == 422
    assert u.post(f"{API}/auth/password/change", json={"current_password": PASSWORD, "new_password": "another-password-1"}).status_code == 200
    assert u.get(f"{API}/auth/me").status_code == 200  # 지금 기기는 유지
    assert phone.get(f"{API}/auth/me").status_code == 401  # 다른 기기는 해제
    assert login(make_client(), u.email, "another-password-1").status_code == 200


def test_mail_failure_does_not_break_registration():
    class Broken:
        def send(self, msg):
            raise OSError("smtp down")

    mail_service.set_backend(Broken())
    try:
        r = make_client().post(f"{API}/auth/register", json=register_payload("mailfail"))
        assert r.status_code == 201
    finally:
        mail_service.set_backend(None)


def test_tokens_never_logged(caplog):
    with caplog.at_level(logging.DEBUG):
        u = UserClient("logcheck", verified=False)
        make_client().post(f"{API}/auth/password/forgot", json={"email": u.email})
    for path in ("/verify-email", "/reset-password"):
        assert last_link(u.email, path) not in caplog.text


def test_mailbox_cli_prints_decoded_link(capsys):
    from app.tasks import main as tasks_main

    u = UserClient("mailbox", verified=False)
    assert tasks_main(["mailbox", "--to", u.email.upper()]) == 0
    out = capsys.readouterr().out
    assert "이메일 주소를 인증해 주세요" in out and f"/verify-email?token={last_link(u.email, '/verify-email')}" in out
    assert tasks_main(["mailbox", "--to", "nobody@example.com"]) == 1
