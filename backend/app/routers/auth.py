from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.ratelimit import login_ip_limiter, login_limiter, register_limiter
from app.core.security import csrf_for_session
from app.dependencies.auth import SESSION_COOKIE, AuthContext, check_origin, require_auth
from app.models import User
from app.schemas.auth import LoginIn, MeOut, RegisterIn
from app.schemas.user import UserBrief
from app.services import auth_service
from app.services.user_view import brief

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _me(user: User, csrf: str) -> MeOut:
    return MeOut(id=str(user.id), email=user.email, username=user.username, display_name=user.display_name, bio=user.bio, csrf_token=csrf)


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.session_ttl_seconds, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")


@router.post("/register", status_code=201, response_model=UserBrief)
def register(data: RegisterIn, request: Request, db: Session = Depends(get_db)):
    check_origin(request)
    register_limiter.hit(_client_ip(request))
    return brief(auth_service.register(db, data))


@router.post("/login", response_model=MeOut)
def login(data: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    check_origin(request)
    ip = _client_ip(request)
    login_ip_limiter.hit(ip)
    login_limiter.hit(f"{ip}|{data.email.strip().lower()}")
    user = auth_service.authenticate(db, data.email, data.password)
    token, csrf = auth_service.create_session(db, user)
    _set_cookie(response, token)
    return _me(user, csrf)


@router.post("/logout", status_code=204)
def logout(response: Response, ctx: AuthContext = Depends(require_auth), db: Session = Depends(get_db)):
    auth_service.revoke_session(db, ctx.session)
    response.delete_cookie(SESSION_COOKIE, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax")
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut)
def me(ctx: AuthContext = Depends(require_auth)):
    return _me(ctx.user, csrf_for_session(ctx.raw_token))
