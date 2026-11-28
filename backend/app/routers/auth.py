from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy.orm import Session

import logging

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.core.errors import AppError
from app.core.ratelimit import forgot_ip_limiter, forgot_limiter, login_ip_limiter, login_limiter, otp_limiter, register_limiter, resend_limiter, token_limiter
from app.core.security import csrf_for_session
from app.dependencies.auth import SESSION_COOKIE, AuthContext, check_origin, require_auth
from app.models import User
from app.schemas.auth import (
    ChangePasswordIn, ForgotPasswordIn, LoginIn, MeOut, MessageOut, OtpCodeIn, PasswordIn, PasswordOtpIn, RecoveryCodesOut,
    RegisterIn, ResetPasswordIn, TokenIn, TwoFactorSetupOut, TwoFactorStatusOut,
)
from app.schemas.user import UserBrief
from app.services import auth_service, mail_service, two_factor_service, user_service

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _me(user: User, csrf: str) -> MeOut:
    return MeOut(
        id=str(user.id), email=user.email, username=user.username, display_name=user.display_name, bio=user.bio,
        email_verified=user.email_verified_at is not None, avatar_url=user_service.avatar_url(user),
        two_factor_enabled=user.two_factor_enabled, is_admin=user.is_admin, csrf_token=csrf,
    )


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.session_ttl_seconds, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")


def _otp_limited(user: User, fn):
    """2단계 인증 코드 확인: 이미 많이 틀렸으면 429, 이번에 틀리면 실패 횟수에 더한다."""
    key = str(user.id)
    otp_limiter.check(key)
    try:
        return fn()
    except AppError as e:
        if e.code == "OTP_INVALID":
            otp_limiter.hit(key)
        raise


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
    # 틀린 코드만 센다 (여러 IP에서 나눠 시도해도 계정당 5분에 5회)
    _otp_limited(user, lambda: two_factor_service.check_login(db, user, data.otp))
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


# ---------- 2단계 인증 (TOTP) ----------

@router.get("/2fa", response_model=TwoFactorStatusOut)
def two_factor_status(ctx: AuthContext = Depends(require_auth), db: Session = Depends(get_db)):
    return TwoFactorStatusOut(enabled=ctx.user.two_factor_enabled, recovery_codes_left=two_factor_service.remaining_codes(db, ctx.user))


@router.post("/2fa/setup", response_model=TwoFactorSetupOut)
def two_factor_setup(data: PasswordIn, ctx: AuthContext = Depends(require_auth), db: Session = Depends(get_db)):
    """설정 시작: 비밀번호 확인 후 인증 앱에 등록할 키(QR 내용)를 준다. /2fa/enable로 코드를 확인해야 켜진다."""
    login_limiter.hit(f"2fa|{ctx.user.id}")
    secret, uri = two_factor_service.setup(db, ctx.user, data.password)
    return TwoFactorSetupOut(secret=secret, otpauth_uri=uri)


@router.post("/2fa/enable", response_model=RecoveryCodesOut)
def two_factor_enable(data: OtpCodeIn, ctx: AuthContext = Depends(require_auth), db: Session = Depends(get_db)):
    codes = _otp_limited(ctx.user, lambda: two_factor_service.enable(db, ctx.user, data.code))
    return RecoveryCodesOut(recovery_codes=codes)


@router.post("/2fa/disable", response_model=MessageOut)
def two_factor_disable(data: PasswordOtpIn, ctx: AuthContext = Depends(require_auth), db: Session = Depends(get_db)):
    login_limiter.hit(f"2fa|{ctx.user.id}")  # 비밀번호 대입 방지
    _otp_limited(ctx.user, lambda: two_factor_service.disable(db, ctx.user, data.password, data.code))
    return MessageOut(message="2단계 인증을 껐습니다.")


@router.post("/2fa/recovery-codes", response_model=RecoveryCodesOut)
def two_factor_new_codes(data: PasswordOtpIn, ctx: AuthContext = Depends(require_auth), db: Session = Depends(get_db)):
    """복구 코드를 새로 만든다 (이전 코드는 모두 무효)."""
    login_limiter.hit(f"2fa|{ctx.user.id}")
    codes = _otp_limited(ctx.user, lambda: two_factor_service.regenerate_codes(db, ctx.user, data.password, data.code))
    return RecoveryCodesOut(recovery_codes=codes)
