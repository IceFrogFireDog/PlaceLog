import base64
import uuid
from datetime import datetime

from sqlalchemy import Select, and_, or_

from app.core.errors import AppError

DEFAULT_LIMIT, MAX_LIMIT = 24, 100


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(MAX_LIMIT, limit))


def encode_cursor(created_at: datetime, id_: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{id_}".encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        ts, id_ = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        dt, cid = datetime.fromisoformat(ts), uuid.UUID(id_)
    except Exception as e:  # noqa: BLE001
        raise AppError(422, "BAD_CURSOR", "잘못된 페이지 커서입니다.") from e
    if dt.tzinfo is None:
        raise AppError(422, "BAD_CURSOR", "잘못된 페이지 커서입니다.")
    return dt, cid


MAX_OFFSET = 10_000


def encode_offset(n: int) -> str:
    return base64.urlsafe_b64encode(f"o:{n}".encode()).decode()


def decode_offset(cursor: str | None) -> int:
    """검색·집계 목록용 오프셋 커서."""
    if not cursor:
        return 0
    try:
        tag, n = base64.urlsafe_b64decode(cursor.encode()).decode().split(":")
        n = int(n)
    except Exception as e:  # noqa: BLE001
        raise AppError(422, "BAD_CURSOR", "잘못된 페이지 커서입니다.") from e
    if tag != "o" or not 0 <= n <= MAX_OFFSET:
        raise AppError(422, "BAD_CURSOR", "잘못된 페이지 커서입니다.")
    return n


def paginate_desc(stmt: Select, created_col, id_col, cursor: str | None, limit: int) -> Select:
    """created_at DESC, id DESC 순 keyset 페이지네이션. limit+1개를 가져와 다음 페이지 여부를 판단한다."""
    if cursor:
        ts, cid = decode_cursor(cursor)
        stmt = stmt.where(or_(created_col < ts, and_(created_col == ts, id_col < cid)))
    return stmt.order_by(created_col.desc(), id_col.desc()).limit(limit + 1)


def split_page(rows: list, limit: int, key=lambda r: (r.created_at, r.id)) -> tuple[list, str | None]:
    if len(rows) > limit:
        rows = rows[:limit]
        return rows, encode_cursor(*key(rows[-1]))
    return rows, None
