# PlaceLog

지구본 위에 장소별로 사진을 기록하고, 공개 범위(전체·친구·나만)에 따라 친구와 나누는 웹 서비스입니다.

| 폴더 | 내용 |
| --- | --- |
| [`backend/`](backend) | API 서버 — FastAPI · PostgreSQL. 실행·설정·API·테스트는 [backend/README.md](backend/README.md), 변경 내역은 [backend/CHANGELOG.md](backend/CHANGELOG.md) |
| [`frontend/`](frontend) | 화면 — Next.js · React · Three.js(지구본) · Leaflet. 실행·설정은 [frontend/README.md](frontend/README.md) |
| `.github/workflows/ci.yml` | 푸시할 때마다 백엔드 테스트(SQLite·PostgreSQL)·마이그레이션 왕복, 화면 린트·타입 검사·빌드를 자동으로 확인 |

개발 기준 문서: [backend/docs/development-spec.md](backend/docs/development-spec.md)

## 빠른 실행 (개발)

1. **백엔드** (`backend/` 폴더): `.env` 만들기 → `docker compose up -d db` → 가상환경·설치 → `alembic upgrade head` → `uvicorn app.main:app --reload --port 8000`. 자세한 순서는 [backend/README.md](backend/README.md).
2. **화면** (`frontend/` 폴더): `npm ci` → `.env.example`을 `.env.local`로 복사 → `npm run dev` → http://localhost:3000
