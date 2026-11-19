import base64
import hashlib
import hmac
import secrets

from app.core.config import settings

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**15, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, maxmem=64 * 1024 * 1024)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${b64(salt)}${b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(hash_b64)
        dk = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p), maxmem=64 * 1024 * 1024, dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


# 존재하지 않는 계정에도 같은 비용을 쓰기 위한 더미 해시 (계정 존재 여부 타이밍 노출 완화)
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_for_session(session_token: str) -> str:
    """세션 토큰에서 결정적으로 유도한 CSRF 토큰. DB에는 해시만 저장한다."""
    return hmac.new(settings.secret_key.encode(), f"csrf:{session_token}".encode(), hashlib.sha256).hexdigest()
