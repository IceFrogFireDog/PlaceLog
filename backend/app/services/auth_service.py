from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import utcnow
from app.core.errors import AppError
from app.core.security import DUMMY_PASSWORD_HASH, csrf_for_session, hash_password, hash_token, new_session_token, verify_password
from app.models import User, UserSession
from app.schemas.auth import RegisterIn


def register(db: Session, data: RegisterIn) -> User:
    fields: dict[str, str] = {}
    if db.scalar(select(User.id).where(User.email == data.email)):
        fields["email"] = "이미 사용 중인 이메일입니다."
    if db.scalar(select(User.id).where(User.username == data.username)):
        fields["username"] = "이미 사용 중인 닉네임입니다."
    if fields:
        raise AppError(409, "DUPLICATE", "이미 사용 중인 정보가 있습니다.", fields)
    user = User(email=data.email, username=data.username, display_name=data.display_name, password_hash=hash_password(data.password), bio="")
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
