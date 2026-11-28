"""운영 작업 명령.

  python -m app.tasks cleanup [--min-age 3600]       고아 파일·만료 세션·만료 토큰 정리 (주기 실행 권장)
  python -m app.tasks duplicates [--radius 200]      같은 이름의 가까운 장소 쌍 출력
  python -m app.tasks merge-places SOURCE TARGET     SOURCE 장소의 사진을 TARGET으로 옮기고 SOURCE 삭제
  python -m app.tasks mailbox [--to EMAIL] [-n 1]    개발용 메일함(MAIL_BACKEND=file)의 최근 메일 읽기
  python -m app.tasks process-pending                멈췄거나 시작되지 않은 사진 변환 작업 처리 (1회)
  python -m app.tasks worker [--interval 5]          위 작업을 계속 반복하고 1시간마다 cleanup 실행 (운영용 상시 프로세스)
  python -m app.tasks disable-2fa EMAIL              인증 앱·복구 코드를 모두 잃어버린 사용자의 2단계 인증 해제 (본인 확인 후)
  python -m app.tasks make-admin EMAIL [--revoke]    관리자 권한 주기·빼기 (관리자 화면 /admin)
"""
import argparse
import email
import logging
import signal
import sys
import time
import uuid
from email import policy
from pathlib import Path

from app.core.config import settings
from app.core.database import SessionLocal
from app.services import maintenance_service, processing_service


def _mailbox(to: str | None, count: int) -> int:
    """.eml 본문은 인코딩되어 있어 편집기로 열면 링크가 안 보이므로 풀어서 출력한다."""
    files = sorted(Path(settings.mail_file_dir).glob("*.eml"), key=lambda p: (p.stat().st_mtime, p.name))
    msgs = [email.message_from_bytes(f.read_bytes(), policy=policy.default) for f in files]
    if to:
        msgs = [m for m in msgs if (m["To"] or "").lower() == to.strip().lower()]
    if not msgs:
        print(f"메일이 없습니다. (폴더: {settings.mail_file_dir}, MAIL_BACKEND={settings.mail_backend})")
        return 1
    for m in msgs[-count:]:
        print(f"받는 사람: {m['To']}\n제목: {m['Subject']}\n날짜: {m['Date']}\n\n{m.get_content().strip()}\n" + "-" * 60)
    return 0


def _worker(interval: float, cleanup_every: float) -> int:
    """변환 작업자. SIGTERM(docker stop)을 받으면 지금 하던 사진까지 끝내고 멈춘다."""
    stop = {"now": False}

    def _stop(*_):
        stop["now"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("app.worker")
    log.info("worker started (interval=%ss)", interval)
    last_cleanup = 0.0
    while not stop["now"]:
        try:
            done = processing_service.process_pending()
            if done["READY"] or done["FAILED"]:
                log.info("processed: %s", done)
            if time.monotonic() - last_cleanup >= cleanup_every:
                with SessionLocal() as db:
                    log.info("cleanup: %s", maintenance_service.cleanup(db))
                last_cleanup = time.monotonic()
        except Exception:  # noqa: BLE001 - DB 재시작 등 일시 오류에도 작업자는 계속 돈다
            log.exception("worker loop error")
        for _ in range(int(interval * 10)):
            if stop["now"]:
                break
            time.sleep(0.1)
    log.info("worker stopped")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.tasks", description="지구본 사진 서비스 운영 작업")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_clean = sub.add_parser("cleanup", help="고아 파일·만료 세션·만료 토큰 정리")
    p_clean.add_argument("--min-age", type=int, default=3600, help="이 초보다 오래된 고아 파일만 삭제 (업로드 중 파일 보호)")
    p_dup = sub.add_parser("duplicates", help="중복 장소 후보 출력")
    p_dup.add_argument("--radius", type=float, default=200)
    p_merge = sub.add_parser("merge-places", help="장소 합치기")
    p_merge.add_argument("source")
    p_merge.add_argument("target")
    sub.add_parser("process-pending", help="멈췄거나 시작되지 않은 사진 변환 작업 처리")
    p_2fa = sub.add_parser("disable-2fa", help="사용자의 2단계 인증 해제 (운영자용)")
    p_2fa.add_argument("email")
    p_admin = sub.add_parser("make-admin", help="관리자 권한 주기·빼기")
    p_admin.add_argument("email")
    p_admin.add_argument("--revoke", action="store_true")
    p_worker = sub.add_parser("worker", help="변환 작업자 (상시 실행, 1시간마다 cleanup 포함)")
    p_worker.add_argument("--interval", type=float, default=5.0, help="작업 확인 간격(초)")
    p_worker.add_argument("--cleanup-every", type=float, default=3600.0, help="cleanup 실행 간격(초)")
    p_mail = sub.add_parser("mailbox", help="개발용 메일함의 최근 메일 출력")
    p_mail.add_argument("--to", help="받는 사람 이메일로 거르기")
    p_mail.add_argument("-n", "--count", type=int, default=1)
    args = parser.parse_args(argv)
    if args.cmd == "mailbox":
        return _mailbox(args.to, max(1, args.count))
    if args.cmd == "worker":
        return _worker(max(0.5, args.interval), max(60.0, args.cleanup_every))
    if args.cmd == "process-pending":
        print("변환 작업: " + ", ".join(f"{k}={v}" for k, v in processing_service.process_pending(limit=1000).items()))
        return 0

    with SessionLocal() as db:
        if args.cmd == "make-admin":
            from sqlalchemy import select

            from app.models import User

            user = db.scalar(select(User).where(User.email == args.email.strip().lower()))
            if user is None:
                print("해당 이메일의 사용자가 없습니다.", file=sys.stderr)
                return 1
            user.is_admin = not args.revoke
            db.commit()
            print(f"{user.email}: 관리자 권한을 {'뺐습니다' if args.revoke else '주었습니다'}.")
            return 0
        if args.cmd == "disable-2fa":
            from sqlalchemy import select

            from app.models import User
            from app.services import two_factor_service

            user = db.scalar(select(User).where(User.email == args.email.strip().lower()))
            if user is None:
                print("해당 이메일의 사용자가 없습니다.", file=sys.stderr)
                return 1
            two_factor_service.clear(db, user)
            print(f"{user.email}의 2단계 인증을 해제했습니다.")
            return 0
        if args.cmd == "cleanup":
            result = maintenance_service.cleanup(db, args.min_age)
            print("정리 완료: " + ", ".join(f"{k}={v}" for k, v in result.items()))
        elif args.cmd == "duplicates":
            pairs = maintenance_service.find_duplicate_places(db, args.radius)
            for a, b, d in pairs:
                print(f"{a.id}\t{a.name}\t↔\t{b.id}\t{b.name}\t{d:.0f}m")
            print(f"중복 후보 {len(pairs)}쌍")
        elif args.cmd == "merge-places":
            try:
                moved = maintenance_service.merge_places(db, uuid.UUID(args.source), uuid.UUID(args.target))
            except ValueError as e:
                print(f"실패: {e}", file=sys.stderr)
                return 1
            print(f"사진 {moved}장을 옮기고 장소를 합쳤습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
