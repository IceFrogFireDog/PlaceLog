"""메일 발송. MAIL_BACKEND=file(개발용: MAIL_FILE_DIR 폴더에 .eml 저장) / smtp(운영) / none(발송 안 함).
메일 본문에는 1회용 링크가 들어가므로 본문·링크를 로그에 남기지 않는다 (지시서 3.5)."""
import logging
import smtplib
import ssl
import time
import uuid
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Protocol

from app.core.config import settings

log = logging.getLogger("app.mail")


class MailBackend(Protocol):
    def send(self, msg: EmailMessage) -> None: ...


class FileMailBackend:
    def __init__(self, directory: str):
        self.dir = Path(directory)

    def send(self, msg: EmailMessage) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        name = f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 10**9:09d}-{uuid.uuid4().hex[:6]}.eml"
        (self.dir / name).write_bytes(bytes(msg))


class SmtpMailBackend:
    def send(self, msg: EmailMessage) -> None:
        ctx = ssl.create_default_context()
        if settings.smtp_ssl:
            server: smtplib.SMTP = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10, context=ctx)
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
        with server:
            if not settings.smtp_ssl and settings.smtp_starttls:
                server.starttls(context=ctx)
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)


class NoneMailBackend:
    def send(self, msg: EmailMessage) -> None:
        log.info("mail disabled; dropped message: %s", msg["Subject"])


_backend: MailBackend | None = None


def get_backend() -> MailBackend:
    global _backend
    if _backend is None:
        _backend = {"file": lambda: FileMailBackend(settings.mail_file_dir), "smtp": SmtpMailBackend, "none": NoneMailBackend}[settings.mail_backend]()
    return _backend


def set_backend(b: MailBackend) -> None:  # 테스트용
    global _backend
    _backend = b


def _mask(addr: str) -> str:
    local, _, domain = addr.partition("@")
    return f"{local[:1]}***@{domain}"


def send_mail(to: str, subject: str, body: str) -> bool:
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain="photo-globe.local")
    msg.set_content(body)
    try:
        get_backend().send(msg)
        return True
    except Exception as e:  # noqa: BLE001 - 메일 실패가 가입·요청 자체를 실패시키지 않게
        log.warning("mail send failed (%s) to=%s", type(e).__name__, _mask(to))
        return False


def verification_mail(display_name: str, link: str) -> tuple[str, str]:
    hours = settings.verify_token_ttl_seconds // 3600
    return (
        "[지구본 사진] 이메일 주소를 인증해 주세요",
        f"{display_name}님, 가입해 주셔서 감사합니다.\n\n"
        f"아래 링크를 눌러 이메일 주소를 인증해 주세요.\n{link}\n\n"
        f"이 링크는 {hours}시간 동안 한 번만 사용할 수 있습니다.\n"
        "본인이 가입하지 않았다면 이 메일을 무시하세요.\n",
    )


def reset_mail(display_name: str, link: str) -> tuple[str, str]:
    minutes = settings.reset_token_ttl_seconds // 60
    return (
        "[지구본 사진] 비밀번호 재설정 안내",
        f"{display_name}님, 비밀번호 재설정 요청을 받았습니다.\n\n"
        f"아래 링크에서 새 비밀번호를 정해 주세요.\n{link}\n\n"
        f"이 링크는 {minutes}분 동안 한 번만 사용할 수 있습니다.\n"
        "본인이 요청하지 않았다면 이 메일을 무시하세요. 비밀번호는 바뀌지 않습니다.\n",
    )
