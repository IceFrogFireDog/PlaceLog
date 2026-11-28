"""2단계 인증(TOTP) 켜기·끄기·로그인 확인·복구 코드."""
from sqlalchemy import delete, or_, update
from sqlalchemy.orm import Session

from app.core import totp
from app.core.database import utcnow
from app.core.errors import AppError
from app.core.security import verify_password
from app.models import RecoveryCode, User

OTP_INVALID = AppError(422, "OTP_INVALID", "인증 코드가 올바르지 않습니다. 인증 앱의 현재 6자리 코드나 복구 코드를 입력해 주세요.",
                       {"code": "코드가 올바르지 않습니다."})


def _check_password(user: User, password: str) -> None:
    if not verify_password(password, user.password_hash):
        raise AppError(422, "INVALID_PASSWORD", "비밀번호가 올바르지 않습니다.", {"password": "비밀번호가 올바르지 않습니다."})


def _new_codes(db: Session, user: User) -> list[str]:
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    codes = totp.new_recovery_codes()
    db.add_all(RecoveryCode(user_id=user.id, code_hash=totp.hash_recovery(c)) for c in codes)
    return codes


def setup(db: Session, user: User, password: str) -> tuple[str, str]:
    """설정 시작: 새 키를 만들어 (키 문자열, otpauth 주소)를 돌려준다. 코드 확인(enable) 전까지는 꺼진 상태."""
    _check_password(user, password)
    if user.two_factor_enabled:
        raise AppError(409, "OTP_ALREADY_ENABLED", "2단계 인증이 이미 켜져 있습니다.")
    user.totp_pending_salt = totp.new_salt()
    db.commit()
    secret = totp.secret_for(user.totp_pending_salt)
    return totp.b32(secret), totp.otpauth_uri(secret, user.email)


def enable(db: Session, user: User, code: str) -> list[str]:
    if user.two_factor_enabled:
        raise AppError(409, "OTP_ALREADY_ENABLED", "2단계 인증이 이미 켜져 있습니다.")
    if not user.totp_pending_salt:
        raise AppError(409, "OTP_SETUP_REQUIRED", "먼저 2단계 인증 설정을 시작해 주세요.")
    step = totp.match_step(totp.secret_for(user.totp_pending_salt), code)
    if step is None:
        raise OTP_INVALID
    user.totp_salt, user.totp_pending_salt = user.totp_pending_salt, None
    user.totp_enabled_at = utcnow()
    user.totp_last_step = step
    codes = _new_codes(db, user)
    db.commit()
    return codes


def verify_second_factor(db: Session, user: User, code: str) -> bool:
    """인증 앱 코드(같은 코드 재사용 불가) 또는 아직 안 쓴 복구 코드면 True. 사용 처리는 원자적으로 한 번만."""
    if not user.two_factor_enabled or not code:
        return False
    step = totp.match_step(totp.secret_for(user.totp_salt), code, after_step=user.totp_last_step)
    if step is not None:
        res = db.execute(
            update(User)
            .where(User.id == user.id, or_(User.totp_last_step.is_(None), User.totp_last_step < step))
            .values(totp_last_step=step)
        )
        db.commit()
        if res.rowcount == 1:
            user.totp_last_step = step
            return True
        return False
    res = db.execute(
        update(RecoveryCode)
        .where(RecoveryCode.user_id == user.id, RecoveryCode.code_hash == totp.hash_recovery(code), RecoveryCode.used_at.is_(None))
        .values(used_at=utcnow())
    )
    db.commit()
    return res.rowcount == 1


def check_login(db: Session, user: User, code: str | None) -> None:
    """비밀번호가 맞은 뒤 호출. 2단계 인증이 켜진 계정이면 코드가 필요하다."""
    if not user.two_factor_enabled:
        return
    if not code:
        raise AppError(401, "OTP_REQUIRED", "2단계 인증 코드를 입력해 주세요.")
    if not verify_second_factor(db, user, code):
        raise AppError(401, "OTP_INVALID", "인증 코드가 올바르지 않습니다.")


def disable(db: Session, user: User, password: str, code: str) -> None:
    _check_password(user, password)
    if not user.two_factor_enabled:
        raise AppError(409, "OTP_NOT_ENABLED", "2단계 인증이 꺼져 있습니다.")
    if not verify_second_factor(db, user, code):
        raise OTP_INVALID
    clear(db, user)


def clear(db: Session, user: User) -> None:
    """2단계 인증 정보를 모두 지운다 (끄기·운영자 해제)."""
    user.totp_salt = user.totp_pending_salt = None
    user.totp_enabled_at = user.totp_last_step = None
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    db.commit()


def regenerate_codes(db: Session, user: User, password: str, code: str) -> list[str]:
    _check_password(user, password)
    if not user.two_factor_enabled:
        raise AppError(409, "OTP_NOT_ENABLED", "2단계 인증이 꺼져 있습니다.")
    if not verify_second_factor(db, user, code):
        raise OTP_INVALID
    codes = _new_codes(db, user)
    db.commit()
    return codes


def remaining_codes(db: Session, user: User) -> int:
    from sqlalchemy import func, select

    return db.scalar(select(func.count()).select_from(RecoveryCode).where(RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None))) or 0
