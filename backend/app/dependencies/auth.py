import hmac
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db, utcnow
from app.core.errors import AppError
from app.core.security import hash_token
from app.models import User, UserSession

SESSION_COOKIE = "pg_session"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class AuthContext:
    user: User
    session: UserSession
    raw_token: str


def check_origin(request: Request) -> None:
    """변경 요청의 Origin/Referer가 허용 목록인지 확인. 둘 다 없으면(비브라우저 클라이언트) CSRF 토큰 검사에 맡긴다."""
    origin = request.headers.get("origin")
    if origin is None:
        referer = request.headers.get("referer")
        if referer:
            from urllib.parse import urlsplit

            p = urlsplit(referer)
            origin = f"{p.scheme}://{p.netloc}"
    if origin is not None and origin.rstrip("/") not in settings.origins:
        raise AppError(403, "BAD_ORIGIN", "허용되지 않은 출처의 요청입니다.")


def _load(request: Request, db: Session) -> AuthContext | None:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(raw)))
    if sess is None or sess.expires_at <= utcnow():
        return None
    user = db.get(User, sess.user_id)
    if user is None:
        return None
    return AuthContext(user=user, session=sess, raw_token=raw)


def _verify_csrf(request: Request, ctx: AuthContext) -> None:
    if request.method in SAFE_METHODS:
        return
    check_origin(request)
    token = request.headers.get(CSRF_HEADER, "")
    if not token or not hmac.compare_digest(hash_token(token), ctx.session.csrf_token_hash):
        raise AppError(403, "CSRF_FAILED", "보안 토큰이 유효하지 않습니다. 새로고침 후 다시 시도해 주세요.")


def optional_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext | None:
    ctx = _load(request, db)
    if ctx is not None:
        _verify_csrf(request, ctx)
    return ctx


def require_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    ctx = _load(request, db)
    if ctx is None:
        raise AppError(401, "UNAUTHORIZED", "로그인이 필요합니다.")
    _verify_csrf(request, ctx)
    return ctx


def optional_user(ctx: AuthContext | None = Depends(optional_auth)) -> User | None:
    return ctx.user if ctx else None


def require_user(ctx: AuthContext = Depends(require_auth)) -> User:
    return ctx.user
