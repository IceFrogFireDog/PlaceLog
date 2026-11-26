# photo-globe-backend

지구본 사진 기록 서비스의 **백엔드(API 서버)** 입니다. 사진을 장소별로 지구본 위에 기록하고, 공개 범위(전체·친구·나만)에 따라 보여 줍니다.
화면(Next.js)은 이 저장소의 [`frontend/`](../frontend) 폴더에 있습니다. 개발 기준 문서: [`docs/development-spec.md`](docs/development-spec.md)

> **현재 단계: 3차 (v0.3.0)** — 이메일 인증 · 비밀번호 재설정 · 프로필 사진 · HEIC · 장소 검색 · 장소 중복 정책 · S3 저장소 · Redis · 정리 작업
> 단계별 변경 내역은 [`CHANGELOG.md`](CHANGELOG.md)에 있습니다.

구성: FastAPI 0.142 · PostgreSQL 16 · SQLAlchemy 2.1 · Alembic · Pydantic v2 · Pillow + pi-heif · httpx · boto3(S3 호환) · Redis · pytest

## 기능

굵은 글씨가 이번 3차에서 추가된 기능입니다.

| 영역 | 기능 |
| --- | --- |
| 기반 | 프로젝트 구조 · 설정(`.env`) · PostgreSQL 연결(UTC 고정) · 공통 오류 응답(`code`·`message`·`field_errors`) · 목록 페이지 형식(`items`·`next_cursor`) |
| DB | 전체 테이블 설계와 마이그레이션 `0001`(사용자·세션·친구·장소·사진) · **`0002`(이메일 인증·프로필 사진·동의)** |
| 계정 | 가입 · 로그인 · 로그아웃 · 내 정보 · HttpOnly 쿠키 세션 · CSRF 토큰 + Origin 검사 · 빈도 제한 · **개인정보 안내 동의(필수) · 이메일 인증(인증 전 쓰기 제한) · 비밀번호 찾기·재설정·변경** |
| 프로필 | 프로필 조회 · 표시명·소개 수정 · 사용자 검색(친구 관계 표시) · 공개 범위에 맞춘 사진·장소 수, 사용자별 사진·장소 목록 · **프로필 사진(정사각형 WebP, 위치정보 제거)** |
| 친구 | 요청 · 받은/보낸 요청 목록 · 수락 · 거절 · 취소 · 해제 · 친구 목록 |
| 장소 | 장소 만들기 · 이름·도시 검색 · 상세 · 장소별 사진 목록 · 200m 안의 기존 장소 후보 안내 · **같은 이름 근처 장소 409 안내(`force`로 강제 생성) · 주소·장소 검색과 좌표→주소(Nominatim·카카오) · 중복 장소 찾기·합치기 명령** |
| 사진 | 업로드(JPEG·PNG·WebP, 20MB) · 실제 형식·해상도 검사 · EXIF(GPS·촬영일·시간대·카메라) 자동 채움 · 공개 범위(전체/친구/나만) · 수정 · 삭제 · **아이폰 HEIC · EXIF 촬영일 사용 여부 선택** |
| 이미지 | 표시용(2400px)·썸네일(480px) WebP 변환(EXIF 제거) · 권한 확인 후 전달 · 원본은 작성자만 |
| 지구본 | 전체/친구/나 모드 · 범위(bbox)·확대 단계별 장소 핀과 격자 클러스터 · 날짜 변경선 처리 · 응답 상한 |
| 운영 | **S3 호환 저장소 · Redis 빈도 제한 · 정리 작업(고아 파일·만료 세션·토큰) · 개발용 메일함 명령** |
| 검사 | 자동 테스트 · GitHub Actions CI(SQLite·PostgreSQL 테스트, 마이그레이션 왕복) |

이메일 인증 전에는 둘러보기·프로필 수정만 되고 **사진 등록·장소 만들기·친구 요청은 막힙니다**. 마이그레이션 `0002` 이전에 가입한 계정은 인증된 것으로 처리합니다.

## 실행 (개발)

아래 명령은 모두 `backend/` 폴더에서 실행합니다. 필요한 것: Python 3.12 이상, Docker(개발용 DB) 또는 직접 설치한 PostgreSQL 16

```bash
cp .env.example .env            # SECRET_KEY 채우기: python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up -d db         # 개발용 PostgreSQL (.env의 POSTGRES_* 값 사용)

python -m venv .venv && source .venv/bin/activate
pip install --require-hashes -r requirements-dev.lock   # 잠금 파일로 검증된 버전 설치
pip install --no-deps -e .
alembic upgrade head            # 빈 DB에 전체 스키마 생성 (새 단계를 받은 뒤에도 실행)
uvicorn app.main:app --reload --port 8000
```

API 문서(Swagger): http://localhost:8000/api/v1/docs

- **인증 메일 확인(개발)**: 기본값 `MAIL_BACKEND=file`은 메일을 실제로 보내지 않고 `dev-mail/`에 `.eml`로 저장합니다. 본문이 인코딩되어 있으니 아래 명령으로 링크를 보세요.

  ```bash
  python -m app.tasks mailbox --to 내이메일@example.com     # 가장 최근 메일 (링크 포함)
  ```

- **장소 검색**: 기본값 `GEOCODER=nominatim`은 OpenStreetMap 공용 서버를 씁니다(인터넷 필요, 서버가 초당 1회로 자동 제한·캐시). 끄려면 `GEOCODER=none`, 국내 검색 품질이 필요하면 `GEOCODER=kakao` + `KAKAO_REST_API_KEY`.

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
| `LOCAL_STORAGE_PATH` | `./storage` | 사진 파일 폴더(비공개). 상대 경로는 이 폴더 기준 |
| `MAX_UPLOAD_BYTES` | 20MB | 사진 한 장 한도 |
| `MAX_IMAGE_PIXELS` | 8000만 | 해상도 한도(이미지 폭탄 방지) |
| `IMAGE_WORKERS` | `2` | 동시에 처리하는 사진 수 (메모리가 작은 서버는 1) |
| `FRONTEND_BASE_URL` | `http://localhost:3000` | 메일 속 링크가 가리킬 화면 주소 |
| `EMAIL_VERIFICATION_REQUIRED` | `true` | 인증 전에는 사진 등록·장소 생성·친구 요청 차단 |
| `VERIFY_TOKEN_TTL_SECONDS` / `RESET_TOKEN_TTL_SECONDS` | 24시간 / 1시간 | 인증·재설정 링크 유효 시간(1회용) |
| `MAIL_BACKEND` | `file` | `file`(개발용 메일함 `MAIL_FILE_DIR`) / `smtp`(`SMTP_HOST`·`SMTP_PORT`·`SMTP_USER`·`SMTP_PASSWORD`·`SMTP_STARTTLS`·`SMTP_SSL`) / `none`. 보내는 사람 `MAIL_FROM` |
| `GEOCODER` | `nominatim` | `nominatim` / `kakao`(`KAKAO_REST_API_KEY`) / `none`. `NOMINATIM_BASE_URL`·`GEOCODER_USER_AGENT`·`GEOCODER_CONTACT_EMAIL`·`GEOCODE_CACHE_SECONDS` |
| `STORAGE_BACKEND` | `local` | `local` / `object`(S3 호환: `OBJECT_STORAGE_BUCKET`·`_ENDPOINT_URL`·`_REGION`·`_ACCESS_KEY_ID`·`_SECRET_ACCESS_KEY`·`_PREFIX`). 버킷은 비공개로 |
| `RATE_LIMIT_BACKEND` | `memory` | 서버 여러 대면 `redis` + `REDIS_URL`. Redis가 죽으면 제한 없이 통과(서비스 중단 방지) |

전체 목록과 설명은 `.env.example`에 있습니다. `.env`는 Git에 올리지 않습니다(`.gitignore`).

## API

| 메서드 | 경로 (`/api/v1` 아래) | 설명 | 단계 |
| --- | --- | --- | --- |
| POST | `/auth/register` | 가입 | 1차 |
| POST | `/auth/login` | 로그인 (쿠키 세션 + `csrf_token` 응답) | 1차 |
| POST | `/auth/logout` | 로그아웃 | 1차 |
| GET | `/auth/me` | 내 정보 (+ `csrf_token`) | 1차 |
| POST | `/auth/email/verify · /auth/email/resend` | 이메일 인증 · 인증 메일 다시 보내기 | 3차 |
| POST | `/auth/password/forgot · /reset · /change` | 비밀번호 찾기 · 재설정 · 변경 | 3차 |
| GET | `/users/search?q=` | 사용자 검색 (관계 표시, 이메일 미포함) | 1차 |
| PATCH | `/users/me` | 표시명·소개 수정 | 1차 |
| GET | `/users/{username}` | 프로필 | 1차 |
| GET | `/users/{username}/photos · /places` | 사용자의 사진·장소 목록 (보이는 것만) | 2차 |
| PUT·DELETE | `/users/me/avatar` | 프로필 사진 등록·삭제 | 3차 |
| POST | `/friends/requests` | 친구 요청 | 1차 |
| GET | `/friends · /friends/requests?direction=` | 친구 목록 · 받은/보낸 요청 | 1차 |
| POST | `/friends/{id}/accept · /reject` | 수락 · 거절 | 1차 |
| DELETE | `/friends/{id}` | 보낸 요청 취소 · 친구 해제 | 1차 |
| GET·POST | `/places` | 장소 검색 · 만들기 (`nearby_candidates` 포함) | 2차 |
| GET | `/places/{id} · /places/{id}/photos` | 장소 상세 · 장소의 사진 | 2차 |
| POST | `/photos` | 사진 등록 (multipart) | 2차 |
| GET·PATCH·DELETE | `/photos/{id}` | 사진 상세 · 수정 · 삭제 | 2차 |
| GET | `/media/{photo_id}/thumbnail · display · original` | 이미지 (권한 확인 후 전달, 원본은 작성자만) | 2차 |
| GET | `/media/avatars/{user_id}/{file_id}` | 프로필 사진 | 3차 |
| GET | `/map/places?mode=&bbox=&zoom=` | 지구본 핀·클러스터 (`WORLD`/`FRIENDS`/`ME`) | 2차 |
| GET | `/geocode/search · /geocode/reverse` | 주소·장소 검색 · 좌표→주소 | 3차 |
| GET | `/health` | 상태 확인 | 1차 |

- 변경 요청(POST·PUT·PATCH·DELETE)은 로그인 응답의 `csrf_token`을 `X-CSRF-Token` 헤더로 보내야 합니다.
- 오류는 `{"code", "message", "field_errors"}` 형식, 목록은 `{"items", "next_cursor"}` 형식입니다.

## 테스트

```bash
pytest                                               # 임시 SQLite
TEST_DATABASE_URL=postgresql+psycopg://...  pytest   # PostgreSQL (권장, 개발 DB와 다른 DB 사용)
```

현재 **91개** 테스트가 SQLite와 PostgreSQL 16에서 모두 통과합니다. GitHub에 올리면 저장소 맨 위의 `.github/workflows/ci.yml`이 같은 검사와 마이그레이션 왕복을 자동으로 실행합니다.

| 파일 | 확인 내용 |
| --- | --- |
| `test_auth.py` | 가입·로그인·로그아웃, 비밀번호·세션 해시 저장, 중복·형식 검사, 같은 실패 메시지, 세션 만료, Origin 차단, 로그인 빈도 제한(공유 IP 고려), 예약 닉네임 |
| `test_friendships.py` | 요청·수락·거절·취소·해제, 자기 요청·중복·역방향 요청, 제삼자 차단, 검색 관계 표시, 페이지 |
| `test_config_and_messages.py` | 상대 경로 저장소 위치, 한국어 조사(을/를), 빈 표시명 거절 |
| `test_input_edges.py` | 이상 입력 422, 촬영일 범위, 국가 코드, DB 오류 때 GPS가 로그에 남지 않음 |
| `test_upload.py` | EXIF(GPS·촬영일·카메라)와 사용 여부, 시간대 없는 촬영일, 방향 보정, 위장 확장자·GIF, 용량·해상도 초과, 손상 EXIF, 저장·DB 실패 시 파일 정리 |
| `test_photo_permissions.py` | 조회자 4종(비로그인·작성자·친구·신청 중) × 공개 범위 3종을 상세·이미지·장소 목록·개수·프로필에서 교차 확인, 원본·수정·삭제 권한, 친구 해제 즉시 반영, 정확 좌표 규칙, 비공개 장소 노출 방지 |
| `test_map.py` | 모드별 핀·개수, 범위·날짜 변경선, 클러스터, 응답 상한 |
| `test_places_duplicates.py` | 같은 이름 근처 장소 409·강제 생성, 이름 정규화, 남의 비공개 장소 숨김 |
| `test_email_auth.py` | 동의 필수, 인증 전 제한, 링크 1회·만료·재발송 제한, 비밀번호 찾기·재설정·변경, 메일 실패 무시, 토큰 로그 미기록, 메일함 명령 |
| `test_avatar_heic.py` | HEIC EXIF·변환, 손상 파일, 프로필 사진 등록·교체·삭제·거절 |
| `test_geocode.py` | Nominatim·카카오(가짜 전송), 캐시, 장애·꺼짐, 사용자별 제한, 초당 1회·대기 상한 |
| `test_storage_ops.py` | S3(moto) 업로드·전달·삭제, 정리 작업, 중복 장소 명령, Redis 빈도 제한 |

외부 서비스는 테스트에서 가짜로 대체합니다: 장소 검색은 `httpx.MockTransport`, S3는 `moto`, Redis는 `fakeredis`.

## 운영 명령

```bash
python -m app.tasks cleanup [--min-age 3600]      # 고아 파일·만료 세션·만료 토큰 정리 (주기 실행 권장)
python -m app.tasks duplicates [--radius 200]     # 같은 이름·200m 이내 장소 쌍 출력
python -m app.tasks merge-places 원본ID 대상ID     # 원본 장소의 사진을 대상으로 옮기고 원본 삭제
python -m app.tasks mailbox [--to 이메일] [-n 1]   # 개발용 메일함 읽기
```

## 설계 메모

- **세션**: 쿠키 `pg_session`(HttpOnly·SameSite=Lax). `sessions` 테이블에는 토큰의 SHA-256 해시만 저장합니다.
- **CSRF**: 토큰을 `HMAC(SECRET_KEY, 세션 토큰)`으로 유도해 `/auth/me`에서도 다시 받을 수 있게 했고, DB에는 그 해시만 둡니다. 변경 요청은 `X-CSRF-Token` 헤더와 Origin/Referer 허용 목록을 함께 검사합니다.
- **비밀번호**: scrypt(표준 라이브러리). 로그인 실패는 계정이 있든 없든 같은 응답·같은 계산 비용입니다.
- **빈도 제한**: 학교·회사처럼 한 IP를 여럿이 쓰는 환경을 고려해 (IP+이메일)당 분당 10회, IP당 120회, 가입은 IP당 20회.
- **친구**: 두 사용자 쌍당 한 행(`user_low_id < user_high_id` + 유일·CHECK 제약). 반대 방향 요청은 자동 수락하지 않고 409 `INCOMING_REQUEST_EXISTS`. 거절·취소·해제는 행 삭제.
- **입력·로그**: NUL 문자는 공통 스키마·URL 검사로 422. 비밀번호·토큰은 로그에 남기지 않고, DB 오류 로그에도 쿼리 값을 찍지 않습니다(`hide_parameters`).
- **권한**: `services/permission_service.py` 한 곳에서 판단합니다. 사진 상세·이미지(`/media`)·장소 목록·개수·프로필 통계·지구본이 모두 이 모듈을 씁니다. 권한 없는 사진은 존재도 숨기도록 404, 보호 이미지는 `Cache-Control: private, no-store`.
- **장소 노출**: 장소는 "보이는 사진이 있거나 본인이 만든 경우"에만 검색·조회됩니다. 비공개 사진만 있는 '우리집' 같은 장소의 이름·좌표가 새지 않고, 남의 숨겨진 장소에 사진을 붙일 수도 없습니다.
- **업로드**: 확장자가 아닌 실제 형식·해상도를 검사하고, 큰 JPEG는 필요한 크기로만 축소 디코딩합니다. 동시 처리 수는 `IMAGE_WORKERS`로 제한하고 대기는 이벤트 루프에서 해 다른 요청을 막지 않습니다. 저장이나 DB 기록이 실패하면 저장한 파일을 지웁니다.
- **위치·시간**: 대표 장소(`place_id`)와 실제 촬영 좌표(`shot_*`)를 분리하고, 정확한 좌표는 본인 또는 `share_exact_location=true`일 때만 보여 줍니다. 시간대가 없는 EXIF 촬영 시각은 추측하지 않습니다. 촬영일은 1826~2099년만 허용.
- **지구본**: zoom 6 이상은 장소 핀, 그 아래는 DB에서 격자 칸별로 묶은 클러스터(GROUP BY). 격자가 경도 -180에서 시작해 칸이 날짜 변경선을 넘지 않으므로 칸 안 평균 좌표가 정확합니다. 응답은 500개 상한(`truncated`).
- **이메일 인증·재설정**: 1회용 토큰은 해시만 저장하고, 새로 발급하면 이전 링크는 무효. 사용 처리는 조건부 UPDATE라 같은 링크를 동시에 눌러도 한 번만 성공합니다. 비밀번호 찾기는 계정 조회부터 응답 뒤 백그라운드에서 해 가입 여부에 따라 응답 내용·시간이 달라지지 않습니다. 재설정하면 모든 기기 로그아웃, 변경하면 지금 기기만 유지.
- **프로필 사진**: 가운데를 정사각형(256px)으로 잘라 WebP로 저장하고 EXIF를 지웁니다. 바꿀 때마다 주소가 달라지므로 공개 캐시를 허용하고 옛 파일은 지웁니다.
- **HEIC**: `pi-heif`(디코딩 전용, GPL 인코더 미포함). HEIF 회전 정보가 적용된 크기로 기록합니다.
- **장소 검색**: 브라우저가 외부 서비스를 직접 부르지 않고 백엔드(`/geocode/*`)를 거칩니다 → 키 보호, 캐시, Nominatim 이용 정책(앱 식별 User-Agent, 초당 1회) 준수. 3초 넘게 기다려야 하면 줄 세우지 않고 바로 503.
- **장소 중복 정책**: 이름을 정규화(NFKC·대소문자·공백·기호 무시)해 200m 안에 같은 이름이 있으면 409 `DUPLICATE_PLACE` + 기존 장소를 돌려줍니다. 비교 대상은 그 사용자가 볼 수 있는 장소뿐이라 남의 비공개 장소 존재가 드러나지 않습니다. 이미 생긴 중복은 `duplicates`·`merge-places` 명령으로 정리.
- **저장소·운영**: 저장소는 `local`/`object`(S3 호환) 어댑터. 정리 작업은 DB에 없는 사진·프로필 사진 파일, 만료 세션, 만료·사용된 토큰을 지우며 업로드 중일 수 있는 1시간 이내 파일은 건드리지 않습니다. 빈도 제한은 메모리 또는 Redis(고정 창, 장애 시 통과).

## 다음 단계 (4차)

사진 변환 작업 큐(업로드 즉시 응답), 카메라 RAW, 2단계 인증, 관리자 기능, 계정 탈퇴, 지구본 조회 성능, 보안 헤더, Docker 운영 배포.
