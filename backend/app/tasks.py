"""운영 작업 명령.

  python -m app.tasks cleanup [--min-age 3600]       고아 파일·만료 세션·만료 토큰 정리 (주기 실행 권장)
  python -m app.tasks duplicates [--radius 200]      같은 이름의 가까운 장소 쌍 출력
  python -m app.tasks merge-places SOURCE TARGET     SOURCE 장소의 사진을 TARGET으로 옮기고 SOURCE 삭제
  python -m app.tasks mailbox [--to EMAIL] [-n 1]    개발용 메일함(MAIL_BACKEND=file)의 최근 메일 읽기
"""
import argparse
import email
import sys
import uuid
from email import policy
from pathlib import Path

from app.core.config import settings
from app.core.database import SessionLocal
from app.services import maintenance_service


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
    p_mail = sub.add_parser("mailbox", help="개발용 메일함의 최근 메일 출력")
    p_mail.add_argument("--to", help="받는 사람 이메일로 거르기")
    p_mail.add_argument("-n", "--count", type=int, default=1)
    args = parser.parse_args(argv)
    if args.cmd == "mailbox":
        return _mailbox(args.to, max(1, args.count))

    with SessionLocal() as db:
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
