"""2단계 인증용 TOTP (RFC 6238: SHA-1, 6자리, 30초). 외부 라이브러리 없이 표준 라이브러리로 구현.

비밀 키는 DB에 그대로 두지 않는다. DB에는 무작위 솔트만 저장하고, 실제 키는 HMAC(SECRET_KEY, 솔트)로 만든다.
→ DB만 유출돼서는 인증 코드를 만들 수 없다. (SECRET_KEY를 바꾸면 등록된 2단계 인증을 다시 설정해야 한다)
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from app.core.config import settings

DIGITS = 6
STEP_SECONDS = 30
WINDOW = 1  # 앞뒤 30초까지 허용 (기기 시계 오차)
ISSUER = "지구본 사진"
_RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # 헷갈리는 i·l·o·0·1 제외


def new_salt() -> str:
    return secrets.token_hex(16)


def secret_for(salt: str) -> bytes:
    return hmac.new(settings.secret_key.encode(), b"totp:" + salt.encode(), hashlib.sha256).digest()[:20]


def b32(secret: bytes) -> str:
    return base64.b32encode(secret).decode().rstrip("=")


def code_at(secret: bytes, step: int) -> str:
    mac = hmac.new(secret, struct.pack(">Q", step), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    value = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % 10**DIGITS
    return f"{value:0{DIGITS}d}"


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def match_step(secret: bytes, code: str, after_step: int | None = None, now: float | None = None) -> int | None:
    """코드가 맞으면 그 time-step을 반환 (같은 코드 재사용을 막기 위해 after_step 이하는 거부)."""
    code = code.strip().replace(" ", "").replace("-", "")
    if not (code.isdigit() and len(code) == DIGITS):
        return None
    cur = current_step(now)
    for step in range(cur - WINDOW, cur + WINDOW + 1):
        if after_step is not None and step <= after_step:
            continue
        if hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def otpauth_uri(secret: bytes, account: str) -> str:
    label = quote(f"{ISSUER}:{account}")
    return f"otpauth://totp/{label}?secret={b32(secret)}&issuer={quote(ISSUER)}&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}"


def new_recovery_codes(n: int = 10) -> list[str]:
    def part() -> str:
        return "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(4))
    return [f"{part()}-{part()}" for _ in range(n)]


def normalize_recovery(code: str) -> str:
    return code.strip().lower().replace(" ", "").replace("-", "")


def hash_recovery(code: str) -> str:
    """복구 코드는 짧으므로 SECRET_KEY를 섞은 HMAC으로 저장 (DB만으로는 대입 공격 불가)."""
    return hmac.new(settings.secret_key.encode(), b"recovery:" + normalize_recovery(code).encode(), hashlib.sha256).hexdigest()
