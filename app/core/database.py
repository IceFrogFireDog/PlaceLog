from collections.abc import Iterator
from datetime import datetime, timezone

from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.core.config import settings

if settings.database_url.startswith("sqlite"):
    _connect_args: dict = {"check_same_thread": False}
else:
    # DB 서버 기본 시간대(예: Asia/Seoul)와 무관하게 UTC로 주고받는다.
    # jit=off: PostgreSQL JIT는 짧은 웹 요청 쿼리를 수십 배 느리게 만든다 (로그인 장소 검색 173ms → 3ms, 10만 사진 기준)
    _connect_args = {"options": "-c timezone=UTC -c jit=off"}
# hide_parameters: DB 오류 로그에 쿼리 값(비밀번호 해시·정확한 GPS 등)이 찍히지 않게 (지시서 3.5)
_pool = {} if settings.database_url.startswith("sqlite") else {"pool_size": 10, "max_overflow": 20}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=_connect_args, hide_parameters=True, **_pool)

# 촬영일 허용 범위. 범위 밖 값은 시간대 변환 시 연도 1~9999를 넘어 읽기 단계에서 오류가 날 수 있다.
MIN_TAKEN_AT = datetime(1826, 1, 1, tzinfo=timezone.utc)  # 현존하는 가장 오래된 사진 무렵
MAX_TAKEN_AT = datetime(2100, 1, 1, tzinfo=timezone.utc)


def taken_at_in_range(value: datetime) -> bool:
    try:
        return MIN_TAKEN_AT <= value.astimezone(timezone.utc) < MAX_TAKEN_AT
    except (OverflowError, ValueError):
        return False
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """항상 UTC aware datetime으로 저장·반환한다 (SQLite 테스트 호환 포함)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime is not allowed; use UTC aware datetime")
        value = value.astimezone(timezone.utc)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
