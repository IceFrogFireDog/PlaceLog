"""빈도 제한. RATE_LIMIT_BACKEND=memory(단일 서버) 또는 redis(여러 서버가 같은 한도를 공유)."""
import logging
import threading
import time
from collections import defaultdict, deque

from app.core.config import settings
from app.core.errors import AppError

log = logging.getLogger("app.ratelimit")

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


class RedisRateLimiter:
    """Redis 고정 창(INCR + EXPIRE) 제한. 여러 백엔드 인스턴스가 한도를 공유한다.
    Redis에 연결할 수 없으면 서비스가 멈추지 않도록 통과시키고 경고만 남긴다(fail-open)."""

    def __init__(self, name: str, limit: int, window_seconds: int, client=None):
        self.name, self.limit, self.window = name, limit, window_seconds
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import redis

            self._client = redis.Redis.from_url(settings.redis_url, socket_timeout=1, socket_connect_timeout=1)
        return self._client

    def hit(self, key: str) -> None:
        bucket = int(time.time() // self.window)
        rkey = f"rl:{self.name}:{key}:{bucket}"
        try:
            pipe = self.client.pipeline()
            pipe.incr(rkey)
            pipe.expire(rkey, self.window + 1)
            count = pipe.execute()[0]
        except Exception as e:  # noqa: BLE001
            log.warning("rate limiter backend unavailable (%s); allowing request", type(e).__name__)
            return
        if count > self.limit:
            raise AppError(429, "TOO_MANY_REQUESTS", TOO_MANY)

    def reset(self) -> None:  # 테스트용
        try:
            for k in self.client.scan_iter(f"rl:{self.name}:*"):
                self.client.delete(k)
        except Exception:  # noqa: BLE001
            pass


_all: list = []


def make_limiter(name: str, limit: int, window_seconds: int):
    lim = RedisRateLimiter(name, limit, window_seconds) if settings.rate_limit_backend == "redis" else MemoryRateLimiter(name, limit, window_seconds)
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
resend_limiter = make_limiter("verify_resend", 3, 600)  # key = 사용자
forgot_limiter = make_limiter("forgot", 3, 600)        # key = 이메일 (메일 폭탄 방지)
forgot_ip_limiter = make_limiter("forgot_ip", 20, 600)  # key = IP
token_limiter = make_limiter("token", 30, 60)          # key = IP (인증·재설정 토큰 대입 방지)
geocode_limiter = make_limiter("geocode", 30, 60)      # key = 사용자
