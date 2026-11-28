# syntax=docker/dockerfile:1
# 지구본 사진 백엔드 (FastAPI). 빌드: docker build -t photo-globe-backend .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 의존성을 먼저 설치해 코드만 바뀌면 이 층을 다시 쓰게 한다. 잠금 파일의 해시와 다르면 설치를 거부한다.
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

# root가 아닌 사용자로 실행. 사진은 /data/storage 볼륨에 저장한다.
RUN useradd --system --uid 10001 --no-create-home --home-dir /nonexistent app \
 && mkdir -p /data/storage \
 && chown -R app:app /data
USER app
ENV LOCAL_STORAGE_PATH=/data/storage \
    MAIL_FILE_DIR=/data/dev-mail \
    WEB_CONCURRENCY=1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"]

# 시작할 때 DB 마이그레이션을 적용한 뒤 서버를 띄운다.
# --forwarded-allow-ips='*'는 백엔드 포트를 밖에 열지 않고 같은 내부망의 Caddy만 접근할 때만 안전하다(compose.prod.yaml 구성).
# WEB_CONCURRENCY를 2 이상으로 올리면 공용 Nominatim의 초당 1회 제한이 프로세스마다 따로 적용되므로 GEOCODER=kakao 등을 쓸 것.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --workers ${WEB_CONCURRENCY}"]
