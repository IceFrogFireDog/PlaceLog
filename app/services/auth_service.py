from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import utcnow
from app.core.errors import AppError
from app.core.security import DUMMY_PASSWORD_HASH, csrf_for_session, hash_password, hash_token, new_session_token, verify_password
from app.models import EmailToken, TokenPurpose, User, UserSession
from app.schemas.auth import RegisterIn
from app.services import email_token_service, mail_service


def register(db: Session, data: RegisterIn) -> User:
    fields: dict[str, str] = {}
    if db.scalar(select(User.id).where(User.email == data.email)):
        fields["email"] = "이미 사용 중인 이메일입니다."
    if db.scalar(select(User.id).where(User.username == data.username)):
        fields["username"] = "이미 사용 중인 닉네임입니다."
    if fields:
        raise AppError(409, "DUPLICATE", "이미 사용 중인 정보가 있습니다.", fields)
    user = User(
        email=data.email, username=data.username, display_name=data.display_name, password_hash=hash_password(data.password), bio="",
        privacy_agreed_at=utcnow(),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as e:  # 동시 가입 경쟁
        db.rollback()
        raise AppError(409, "DUPLICATE", "이미 사용 중인 정보가 있습니다.") from e
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    ok = verify_password(password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if user is None or not ok:
        raise AppError(401, "INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다.")
    return user


def create_session(db: Session, user: User) -> tuple[str, str]:
    """(세션 토큰 원문, CSRF 토큰 원문)을 반환. DB에는 해시만 저장."""
    now = utcnow()
    db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at <= now))
    token = new_session_token()
    csrf = csrf_for_session(token)
    db.add(UserSession(user_id=user.id, token_hash=hash_token(token), csrf_token_hash=hash_token(csrf), expires_at=now + timedelta(seconds=settings.session_ttl_seconds)))
    db.commit()
    return token, csrf


def revoke_session(db: Session, session: UserSession) -> None:
    db.delete(session)
    db.commit()


# ---------- 이메일 인증 ----------

def prepare_verification_mail(db: Session, user: User) -> tuple[str, str, str] | None:
    """인증 토큰을 발급하고 (받는 사람, 제목, 본문)을 반환한다. 이미 인증됐으면 None.
    실제 발송은 응답 뒤 백그라운드에서 한다 (메일 서버 지연이 응답 시간에 드러나지 않게)."""
    if user.email_verified_at is not None:
        return None
    raw = email_token_service.issue(db, user, TokenPurpose.VERIFY, settings.verify_token_ttl_seconds)
    subject, body = mail_service.verification_mail(user.display_name, f"{settings.frontend_base_url}/verify-email?token={raw}")
    return user.email, subject, body


def verify_email(db: Session, raw: str) -> User:
    user = email_token_service.consume(db, raw, TokenPurpose.VERIFY)
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    db.commit()
    return user


# ---------- 비밀번호 재설정·변경 ----------

def prepare_reset_mail(db: Session, email: str) -> tuple[str, str, str] | None:
    """가입된 이메일이면 재설정 토큰을 발급한다. 없는 이메일이어도 호출자는 같은 응답을 준다 (계정 존재 노출 방지)."""
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        return None
    raw = email_token_service.issue(db, user, TokenPurpose.RESET, settings.reset_token_ttl_seconds)
    subject, body = mail_service.reset_mail(user.display_name, f"{settings.frontend_base_url}/reset-password?token={raw}")
    return user.email, subject, body


def reset_password(db: Session, raw: str, new_password: str) -> None:
    user = email_token_service.consume(db, raw, TokenPurpose.RESET)
    user.password_hash = hash_password(new_password)
    if user.email_verified_at is None:  # 메일 링크를 받았으므로 주소 소유가 확인됨
        user.email_verified_at = utcnow()
    # 다른 기기에 남아 있던 로그인과 다른 재설정 링크를 모두 무효화
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.execute(delete(EmailToken).where(EmailToken.user_id == user.id, EmailToken.purpose == TokenPurpose.RESET.value, EmailToken.used_at.is_(None)))
    db.commit()


def change_password(db: Session, user: User, current: str, new: str, keep_session: UserSession) -> None:
    if not verify_password(current, user.password_hash):
        raise AppError(422, "INVALID_PASSWORD", "현재 비밀번호가 올바르지 않습니다.", {"current_password": "현재 비밀번호가 올바르지 않습니다."})
    if current == new:
        raise AppError(422, "VALIDATION_ERROR", "새 비밀번호가 현재 비밀번호와 같습니다.", {"new_password": "현재와 다른 비밀번호를 입력해 주세요."})
    user.password_hash = hash_password(new)
    # 지금 쓰는 세션만 남기고 다른 기기의 로그인은 끊는다
    db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.id != keep_session.id))
    db.commit()
