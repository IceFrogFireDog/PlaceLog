# photo-globe-backend

지구본 사진 기록 서비스의 **백엔드(API 서버)** 입니다. 사진을 장소별로 지구본 위에 기록하고, 공개 범위(전체·친구·나만)에 따라 보여 줍니다.
화면(Next.js)은 이 저장소의 [`frontend/`](../frontend) 폴더에 있습니다. 개발 기준 문서: [`docs/development-spec.md`](docs/development-spec.md)

변경 내역은 [`CHANGELOG.md`](CHANGELOG.md)에 있습니다.

구성: FastAPI 0.142 · PostgreSQL 16 · SQLAlchemy 2.1 · Alembic · Pydantic v2 · pytest

## 기능

| 영역 | 기능 |
| --- | --- |
| 기반 | 프로젝트 구조 · 설정(`.env`) · PostgreSQL 연결(UTC 고정) · 공통 오류 응답(`code`·`message`·`field_errors`) · 목록 페이지 형식(`items`·`next_cursor`) |
| DB | 전체 테이블 설계와 마이그레이션 `0001`(사용자·세션·친구·장소·사진) |
| 계정 | 가입 · 로그인 · 로그아웃 · 내 정보 · HttpOnly 쿠키 세션 · CSRF 토큰 + Origin 검사 · 빈도 제한 |
| 프로필 | 프로필 조회 · 표시명·소개 수정 · 사용자 검색(친구 관계 표시) |
| 친구 | 요청 · 받은/보낸 요청 목록 · 수락 · 거절 · 취소 · 해제 · 친구 목록 |
| 검사 | 자동 테스트 · GitHub Actions CI(SQLite·PostgreSQL 테스트, 마이그레이션 왕복) |

장소·사진 테이블은 DB 설계 때 함께 만들어 두었고, API는 아직 연결하지 않았습니다.

## 실행 (개발)

아래 명령은 모두 `backend/` 폴더에서 실행합니다. 필요한 것: Python 3.12 이상, Docker(개발용 DB) 또는 직접 설치한 PostgreSQL 16

```bash
cp .env.example .env            # SECRET_KEY 채우기: python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up -d db         # 개발용 PostgreSQL (.env의 POSTGRES_* 값 사용)

python -m venv .venv && source .venv/bin/activate
pip install --require-hashes -r requirements-dev.lock   # 잠금 파일로 검증된 버전 설치
pip install --no-deps -e .
alembic upgrade head            # 빈 DB에 전체 스키마 생성 (새 코드를 받은 뒤에도 실행)
uvicorn app.main:app --reload --port 8000
```

API 문서(Swagger): http://localhost:8000/api/v1/docs

<details>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # 출력값을 .env의 SECRET_KEY=에 붙여넣기
docker compose up -d db
py -m venv .venv
.\.venv\Scripts\Activate.ps1          # 실행 정책 오류 시: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install --require-hashes -r requirements-dev.lock
pip install --no-deps -e .
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

테스트(PostgreSQL): `$env:TEST_DATABASE_URL="postgresql+psycopg://..."; pytest`
</details>

## 설정 (`.env`)

| 설정 | 기본값 | 설명 |
| --- | --- | --- |
| `DATABASE_URL` | (필수) | `postgresql+psycopg://사용자:비밀번호@호스트:5432/DB이름` |
| `SECRET_KEY` | (필수) | 32자 이상 랜덤값. CSRF 토큰 유도에 사용 (바꾸면 모두 다시 로그인해야 함) |
| `SESSION_TTL_SECONDS` | 14일 | 로그인 유지 시간 |
| `COOKIE_SECURE` | `true` | 로컬 http 개발에서만 `false`, 배포(https)에서는 반드시 `true` |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | 변경 요청을 허용할 화면 주소(쉼표로 여러 개) |
| `POSTGRES_USER`·`_PASSWORD`·`_DB` | photoglobe / change-me | 개발용 DB 컨테이너(`compose.yaml`) 계정. 바꾸면 `DATABASE_URL`도 같이 |

전체 목록과 설명은 `.env.example`에 있습니다. `.env`는 Git에 올리지 않습니다(`.gitignore`).

## API

| 메서드 | 경로 (`/api/v1` 아래) | 설명 |
| --- | --- | --- |
| POST | `/auth/register` | 가입 |
| POST | `/auth/login` | 로그인 (쿠키 세션 + `csrf_token` 응답) |
| POST | `/auth/logout` | 로그아웃 |
| GET | `/auth/me` | 내 정보 (+ `csrf_token`) |
| GET | `/users/search?q=` | 사용자 검색 (관계 표시, 이메일 미포함) |
| PATCH | `/users/me` | 표시명·소개 수정 |
| GET | `/users/{username}` | 프로필 |
| POST | `/friends/requests` | 친구 요청 |
| GET | `/friends · /friends/requests?direction=` | 친구 목록 · 받은/보낸 요청 |
| POST | `/friends/{id}/accept · /reject` | 수락 · 거절 |
| DELETE | `/friends/{id}` | 보낸 요청 취소 · 친구 해제 |
| GET | `/health` | 상태 확인 |

- 변경 요청(POST·PUT·PATCH·DELETE)은 로그인 응답의 `csrf_token`을 `X-CSRF-Token` 헤더로 보내야 합니다.
- 오류는 `{"code", "message", "field_errors"}` 형식, 목록은 `{"items", "next_cursor"}` 형식입니다.

## 테스트

```bash
pytest                                               # 임시 SQLite
TEST_DATABASE_URL=postgresql+psycopg://...  pytest   # PostgreSQL (권장, 개발 DB와 다른 DB 사용)
```

현재 **20개** 테스트가 SQLite와 PostgreSQL 16에서 모두 통과합니다. GitHub에 올리면 저장소 맨 위의 `.github/workflows/ci.yml`이 같은 검사와 마이그레이션 왕복을 자동으로 실행합니다.

| 파일 | 확인 내용 |
| --- | --- |
| `test_auth.py` | 가입·로그인·로그아웃, 비밀번호·세션 해시 저장, 중복·형식 검사, 같은 실패 메시지, 세션 만료, Origin 차단, 로그인 빈도 제한(공유 IP 고려), 예약 닉네임 |
| `test_friendships.py` | 요청·수락·거절·취소·해제, 자기 요청·중복·역방향 요청, 제삼자 차단, 검색 관계 표시, 페이지 |
| `test_config_and_messages.py` | 설정 파일 경로, 한국어 조사(을/를), 빈 표시명 거절 |
| `test_input_edges.py` | NUL 문자 같은 이상 입력이 500이 아닌 422 |

## 설계 메모

- **세션**: 쿠키 `pg_session`(HttpOnly·SameSite=Lax). `sessions` 테이블에는 토큰의 SHA-256 해시만 저장합니다.
- **CSRF**: 토큰을 `HMAC(SECRET_KEY, 세션 토큰)`으로 유도해 `/auth/me`에서도 다시 받을 수 있게 했고, DB에는 그 해시만 둡니다. 변경 요청은 `X-CSRF-Token` 헤더와 Origin/Referer 허용 목록을 함께 검사합니다.
- **비밀번호**: scrypt(표준 라이브러리). 로그인 실패는 계정이 있든 없든 같은 응답·같은 계산 비용입니다.
- **빈도 제한**: 학교·회사처럼 한 IP를 여럿이 쓰는 환경을 고려해 (IP+이메일)당 분당 10회, IP당 120회, 가입은 IP당 20회.
- **친구**: 두 사용자 쌍당 한 행(`user_low_id < user_high_id` + 유일·CHECK 제약). 반대 방향 요청은 자동 수락하지 않고 409 `INCOMING_REQUEST_EXISTS`. 거절·취소·해제는 행 삭제.
- **입력·로그**: NUL 문자는 공통 스키마·URL 검사로 422. 비밀번호·토큰은 로그에 남기지 않고, DB 오류 로그에도 쿼리 값을 찍지 않습니다(`hide_parameters`).
