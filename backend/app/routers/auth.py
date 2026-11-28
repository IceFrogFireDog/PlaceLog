from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy.orm import Session

import logging

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.core.ratelimit import forgot_ip_limiter, forgot_limiter, login_ip_limiter, login_limiter, register_limiter, resend_limiter, token_limiter
from app.core.security import csrf_for_session
from app.dependencies.auth import SESSION_COOKIE, AuthContext, check_origin, require_auth
from app.models import User
from app.schemas.auth import ChangePasswordIn, ForgotPasswordIn, LoginIn, MeOut, MessageOut, RegisterIn, ResetPasswordIn, TokenIn
from app.schemas.user import UserBrief
from app.services import auth_service, mail_service, user_service

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _me(user: User, csrf: str) -> MeOut:
    return MeOut(
        id=str(user.id), email=user.email, username=user.username, display_name=user.display_name, bio=user.bio,
        email_verified=user.email_verified_at is not None, avatar_url=user_service.avatar_url(user), csrf_token=csrf,
    )


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.session_ttl_seconds, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")


def _send_later(tasks: BackgroundTasks, mail: tuple[str, str, str] | None) -> None:
    if mail is not None:
        tasks.add_task(mail_service.send_mail, *mail)


@router.post("/register", status_code=201, response_model=UserBrief)
def register(data: RegisterIn, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    check_origin(request)
    register_limiter.hit(_client_ip(request))
    user = auth_service.register(db, data)
    _send_later(tasks, auth_service.prepare_verification_mail(db, user))
    return user_service.brief(user)


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


# ---------- 이메일 인증 ----------

@router.post("/email/verify", response_model=MessageOut)
def verify_email(data: TokenIn, request: Request, db: Session = Depends(get_db)):
    """메일 링크로 연 화면에서 호출. 다른 브라우저에서 열 수도 있으므로 로그인은 필요 없다."""
    check_origin(request)
    token_limiter.hit(_client_ip(request))
    auth_service.verify_email(db, data.token)
    return MessageOut(message="이메일 인증이 완료되었습니다.")


@router.post("/email/resend", status_code=202, response_model=MessageOut)
def resend_verification(tasks: BackgroundTasks, ctx: AuthContext = Depends(require_auth), db: Session = Depends(get_db)):
    if ctx.user.email_verified_at is not None:
        return MessageOut(message="이미 인증된 이메일입니다.")
    resend_limiter.hit(str(ctx.user.id))
    _send_later(tasks, auth_service.prepare_verification_mail(db, ctx.user))
    return MessageOut(message="인증 메일을 다시 보냈습니다.")


# ---------- 비밀번호 ----------

def _reset_mail_job(email: str) -> None:
    """응답을 보낸 뒤 실행한다. 계정 조회·토큰 발급까지 여기서 해야 가입 여부에 따라 응답 시간이 달라지지 않는다."""
    try:
        with SessionLocal() as db:
            mail = auth_service.prepare_reset_mail(db, email)
    except Exception as e:  # noqa: BLE001
        log.warning("reset mail job failed (%s)", type(e).__name__)
        return
    if mail is not None:
        mail_service.send_mail(*mail)


@router.post("/password/forgot", status_code=202, response_model=MessageOut)
def forgot_password(data: ForgotPasswordIn, request: Request, tasks: BackgroundTasks):
    check_origin(request)
    forgot_ip_limiter.hit(_client_ip(request))
    forgot_limiter.hit(data.email)
    tasks.add_task(_reset_mail_job, data.email)
    # 가입 여부와 상관없이 같은 응답·같은 처리 시간 (계정 존재 노출 방지)
    return MessageOut(message="가입된 이메일이라면 비밀번호 재설정 링크를 보냈습니다. 메일함을 확인해 주세요.")


@router.post("/password/reset", response_model=MessageOut)
def reset_password(data: ResetPasswordIn, request: Request, db: Session = Depends(get_db)):
    check_origin(request)
    token_limiter.hit(_client_ip(request))
    auth_service.reset_password(db, data.token, data.password)
    return MessageOut(message="비밀번호를 바꿨습니다. 새 비밀번호로 로그인해 주세요.")


@router.post("/password/change", response_model=MessageOut)
def change_password(data: ChangePasswordIn, ctx: AuthContext = Depends(require_auth), db: Session = Depends(get_db)):
    login_limiter.hit(f"change|{ctx.user.id}")  # 현재 비밀번호 대입 방지
    auth_service.change_password(db, ctx.user, data.current_password, data.new_password, ctx.session)
    return MessageOut(message="비밀번호를 바꿨습니다. 다른 기기의 로그인은 해제되었습니다.")
