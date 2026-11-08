# PlaceLog

지구본 위에 장소별로 사진을 기록하고, 공개 범위(전체·친구·나만)에 따라 친구와 나누는 웹 서비스입니다.

| 폴더 | 내용 |
| --- | --- |
| [`backend/`](backend) | API 서버 — FastAPI · PostgreSQL. 실행·설정·API·테스트는 [backend/README.md](backend/README.md), 단계별 변경 내역은 [backend/CHANGELOG.md](backend/CHANGELOG.md) |
| [`frontend/`](frontend) | 화면 — Next.js · React · Three.js(지구본) · Leaflet. 실행·설정은 [frontend/README.md](frontend/README.md) |
| `.github/workflows/ci.yml` | 푸시할 때마다 백엔드 테스트(SQLite·PostgreSQL)·마이그레이션 왕복, 화면 린트·타입 검사·빌드를 자동으로 확인 |

개발 기준 문서: [backend/docs/development-spec.md](backend/docs/development-spec.md)

## 빠른 실행 (개발)

1. **백엔드** (`backend/` 폴더): `.env` 만들기 → `docker compose up -d db` → 가상환경·설치 → `alembic upgrade head` → `uvicorn app.main:app --reload --port 8000`. 자세한 순서는 [backend/README.md](backend/README.md).
2. **화면** (`frontend/` 폴더): `npm ci` → `.env.example`을 `.env.local`로 복사 → `npm run dev` → http://localhost:3000

## 단계별 계획

백엔드는 단계별로 올라갑니다. 지금 올라와 있는 단계는 [backend/README.md](backend/README.md) 맨 위에 적혀 있습니다.

| 단계 | 백엔드 기능 |
| --- | --- |
| 1차 | 프로젝트 기반 · DB 설계 · 계정(가입·로그인·세션) · 프로필 · 친구 |
| 2차 | 장소 · 사진 업로드(EXIF) · 공개 범위 권한 · 이미지 전달 · 지구본 API |
| 3차 | 이메일 인증 · 비밀번호 재설정 · 프로필 사진 · HEIC · 장소 검색 · 장소 중복 정책 · S3 저장소 · Redis · 정리 작업 |
| 4차 | 사진 변환 작업 큐 · 카메라 RAW · 2단계 인증 · 관리자 · 계정 탈퇴 · 지구본 성능 · 보안 헤더 · Docker 배포 |

화면(`frontend/`)은 4차 기준으로 만들어져 있고, 백엔드가 앞 단계일 때는 그 단계에 있는 기능만 보입니다.
