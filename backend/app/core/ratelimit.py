"""빈도 제한 (프로세스 메모리 기반, 서버 1대 기준)."""
import threading
import time
from collections import defaultdict, deque

from app.core.errors import AppError

TOO_MANY = "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요."


class MemoryRateLimiter:
    """프로세스 메모리 기반 슬라이딩 창 제한."""

    def __init__(self, name: str, limit: int, window_seconds: int):
        self.name, self.limit, self.window = name, limit, window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - self.window:
                q.popleft()
            if len(self._hits) > 10_000:  # 오래된 키 정리 (메모리 무한 증가 방지)
                for k in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window]:
                    del self._hits[k]
                q = self._hits[key]
            if len(q) >= self.limit:
                raise AppError(429, "TOO_MANY_REQUESTS", TOO_MANY)
            q.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


_all: list = []


def make_limiter(name: str, limit: int, window_seconds: int):
    lim = MemoryRateLimiter(name, limit, window_seconds)
    _all.append(lim)
    return lim


def reset_all() -> None:
    for lim in _all:
        lim.reset()


# 학교·회사처럼 한 공인 IP를 여러 명이 쓰는 환경을 고려:
# 계정 대입은 (IP, 이메일)당 10회/분으로 막고, IP 전체는 넉넉하게 둔다.
login_limiter = make_limiter("login", 10, 60)          # key = IP + 이메일
login_ip_limiter = make_limiter("login_ip", 120, 60)   # key = IP
register_limiter = make_limiter("register", 20, 60)    # key = IP
