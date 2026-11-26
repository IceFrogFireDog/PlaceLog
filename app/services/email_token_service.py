"""이메일 인증·비밀번호 재설정용 1회성 토큰."""
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.core.errors import AppError
from app.core.security import hash_token, new_session_token
from app.models import EmailToken, TokenPurpose, User

INVALID = AppError(422, "TOKEN_INVALID", "링크가 만료되었거나 이미 사용되었습니다. 다시 요청해 주세요.")


def issue(db: Session, user: User, purpose: TokenPurpose, ttl_seconds: int) -> str:
    """같은 목적의 이전 미사용 토큰은 무효화하고 새 토큰 원문을 반환한다 (DB에는 해시만)."""
    db.execute(delete(EmailToken).where(EmailToken.user_id == user.id, EmailToken.purpose == purpose.value, EmailToken.used_at.is_(None)))
    raw = new_session_token()
    db.add(EmailToken(user_id=user.id, purpose=purpose.value, token_hash=hash_token(raw), expires_at=utcnow() + timedelta(seconds=ttl_seconds)))
    db.commit()
    return raw


def consume(db: Session, raw: str, purpose: TokenPurpose) -> User:
    """유효한 토큰이면 사용 처리(원자적으로 한 번만)하고 사용자를 반환한다. 커밋은 호출자가 한다."""
    if not raw or len(raw) > 200:
        raise INVALID
    now = utcnow()
    tok = db.scalar(select(EmailToken).where(EmailToken.token_hash == hash_token(raw), EmailToken.purpose == purpose.value))
    if tok is None or tok.used_at is not None or tok.expires_at <= now:
        raise INVALID
    # 동시에 같은 링크를 두 번 눌러도 한 번만 성공하도록 조건부 갱신
    res = db.execute(update(EmailToken).where(EmailToken.id == tok.id, EmailToken.used_at.is_(None)).values(used_at=now))
    if res.rowcount != 1:
        db.rollback()
        raise INVALID
    user = db.get(User, tok.user_id)
    if user is None:
        db.rollback()
        raise INVALID
    return user
