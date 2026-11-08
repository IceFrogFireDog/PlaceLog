# photo-globe-frontend

지구본 사진 기록 서비스의 **화면(웹 프론트엔드)** 입니다. 지구본에서 장소를 고르고, 장소별 사진을 공개 범위(전체·친구·나만)에 따라 봅니다.
API 서버는 이 저장소의 [`backend/`](../backend) 폴더에 있습니다. 이 화면은 백엔드 **4차(v0.4.0)** API 기준으로 만들어져 2단계 인증·관리자·사진 변환 상태 등 전체 기능을 씁니다.

> 백엔드가 아직 1~3차여도 그 단계에 있는 흐름(1차: 가입·로그인·프로필·친구 / 2차: 사진·장소·지구본 / 3차: 이메일 인증·프로필 사진·비밀번호 변경)은 그대로 동작합니다. 백엔드가 보내지 않는 기능(프로필 사진·비밀번호 변경·2단계 인증·계정 삭제 등)은 설정 화면에서 숨기고, 사진 변환 상태가 없으면 등록이 끝난 사진으로 봅니다. 주소 검색(3차)처럼 화면에 남는 일부 버튼은 그 단계 전에는 오류 안내가 뜹니다.

구성: Next.js 16 (App Router, TypeScript) · React 19 · Three.js(지구본) · Leaflet(지도에서 위치 고르기) · exifr(브라우저 EXIF 읽기) · qrcode-generator(2단계 인증 QR) · ESLint 9

## 화면

| 경로 | 내용 |
| --- | --- |
| `/` | 지구본: 전체/친구/나 모드, 장소 핀·클러스터, 마우스 툴팁(장소명·사진 수), 확대 시 상세 해안선, 장소 패널. WebGL이 없으면 장소 목록 |
| `/register` · `/login` | 가입(개인정보 안내 동의 필수) · 로그인(2단계 인증 코드 단계 포함) |
| `/verify-email` · `/forgot-password` · `/reset-password` | 메일 링크로 이메일 인증 · 비밀번호 찾기 · 재설정 (주소창에서 토큰 제거) |
| `/upload` | 사진 여러 장(최대 20장) 등록: JPEG·PNG·WebP·HEIC 장당 20MB, 카메라 RAW 80MB. EXIF GPS·촬영일 자동 채움, 장소 검색·지도에서 고르기, 중복 장소 안내, 사진별 성공·실패 표시 |
| `/photos/[id]` · `/photos/[id]/edit` | 사진 상세(변환 중이면 자동 새로 고침, 실패하면 다시 시도, 관리자 삭제) · 수정·삭제 |
| `/places/[id]` | 장소의 사진 목록 |
| `/users/[username]` | 프로필(사진·장소 목록, 친구 요청 버튼) |
| `/friends` | 친구 · 받은/보낸 요청 |
| `/settings/profile` | 프로필 사진 · 표시명·소개 · 비밀번호 변경 · 2단계 인증(QR·복구 코드) · 계정 삭제 |
| `/admin` | 관리자: 통계 · 사용자 검색·이용 정지 · 중복 장소 합치기 (관리자에게만 메뉴 표시) |
| `/privacy` | 개인정보 처리 안내 (운영 정보는 환경변수로) |

## 실행 (개발)

아래 명령은 모두 `frontend/` 폴더에서 실행합니다. 필요한 것: Node.js 20.9 이상(권장 22·24), 실행 중인 백엔드(기본 http://localhost:8000)

```bash
npm ci
cp .env.example .env.local      # Windows: copy .env.example .env.local
npm run dev                     # http://localhost:3000
```

브라우저는 같은 출처의 `/api/v1/*`만 호출하고 Next가 백엔드로 전달합니다(`next.config.ts`의 rewrites). 그래서 세션 쿠키·CSRF가 같은 도메인에서 동작합니다. 백엔드 `.env`의 `ALLOWED_ORIGINS`·`FRONTEND_BASE_URL`에 이 화면 주소(기본 `http://localhost:3000`)가 들어 있어야 합니다.

## 설정 (`.env.local`)

| 설정 | 설명 |
| --- | --- |
| `API_ORIGIN` | 백엔드 주소 (기본 `http://localhost:8000`) |
| `NEXT_PUBLIC_MAP_TILE_URL` · `NEXT_PUBLIC_MAP_ATTRIBUTION` | 지도에서 고르기 화면의 타일 서버·출처 표시. 비우면 OpenStreetMap 공용 타일(소규모·저빈도 이용만 허용) |
| `NEXT_PUBLIC_PRIVACY_OFFICER` · `_EMAIL` · `_PROCESSORS` · `_EFFECTIVE_DATE` | `/privacy`에 표시할 책임자·연락처·위탁 업체·시행일 |

- **빌드 주의**: rewrites 주소(`API_ORIGIN`)와 `NEXT_PUBLIC_*` 값은 `next build` 시점에 고정됩니다. `.env.local`에 두거나 빌드할 때 지정하세요(`next start`에만 지정하면 반영되지 않음). `NEXT_PUBLIC_*`는 브라우저에 그대로 보이므로 비밀값을 넣지 마세요.
- **업로드 한도**: 개발 프록시 한도는 `next.config.ts`의 `proxyClientMaxBodySize`(90mb)입니다. 백엔드의 `MAX_UPLOAD_BYTES`·`MAX_RAW_UPLOAD_BYTES`를 바꾸면 이 값과 `src/components/PhotoUploadForm.tsx`의 안내 한도도 함께 맞추세요(최종 검사는 서버).

## 검사·빌드

```bash
npm run lint         # ESLint (Next 규칙)
npm run typecheck    # tsc --noEmit
npm run build        # 프로덕션 빌드 → npm start
npm audit --omit=dev # 의존성 보안 권고
```

GitHub에 올리면 저장소 맨 위의 `.github/workflows/ci.yml`이 린트·타입 검사·빌드·`npm audit`·Docker 이미지 빌드를 자동으로 확인합니다.

**Docker**: `docker build -t photo-globe-frontend .` (Next.js standalone 이미지). 운영 배포는 백엔드 4차의 `backend/compose.prod.yaml`이 이 폴더를 빌드해 함께 띄웁니다.

## 브라우저 E2E (Playwright, 28단계)

빈 DB의 백엔드와 이 화면을 띄운 상태에서 가입부터 계정 삭제까지 실제 브라우저로 확인합니다. 백엔드 4차 기준이며, 백엔드 폴더는 같은 저장소의 `backend/`를 자동으로 찾습니다(다른 곳이면 `E2E_BACKEND_DIR`). 장소 검색은 가짜 Nominatim을 씁니다.

```bash
# 1) 가짜 장소 검색 서버
python e2e/mock_nominatim.py 8099 &
# 2) 백엔드 (backend 폴더, 가상환경 활성화): .env에 MAIL_BACKEND=file, GEOCODER=nominatim,
#    NOMINATIM_BASE_URL=http://127.0.0.1:8099 를 넣고 빈 DB에서
alembic upgrade head && uvicorn app.main:app --port 8000 &
# 3) 화면 (이 폴더)
npm run build && npm start &
# 4) 실행
cd e2e && npm install && npx playwright install chromium && npm test
```

백엔드 가상환경이 `backend/.venv`가 아니면 `E2E_PYTHON=파이썬경로`, 화면 주소가 다르면 `E2E_BASE=http://...`를 지정합니다. 실패하면 `e2e/.tmp/shots/`에 화면을 저장합니다.

흐름: 가입(동의 필수) → 인증 전 차단 → 인증 메일 재발송 → 링크로 인증 → JPEG GPS·촬영일 자동 채움 → 주소 검색으로 새 장소 → 지도 클릭 → 좌표로 도시·국가 채우기 → 등록 → HEIC·PNG·시간대 없는 JPEG 동시 등록 → 프로필 사진 → 비밀번호 변경(다른 기기 로그아웃) → 모바일 화면에서 두 번째 사용자 → 중복 장소 안내 → 친구 요청·수락·친구 공개 사진 → 비밀번호 찾기·재설정 → 2단계 인증 켜기·코드 로그인·복구 코드로 끄기 → 관리자 지정·이용 정지/해제 → 지구본 툴팁·상세 해안선 → 개인정보 안내 → 사진 수정·삭제 → 변환 실패 사진 → 카메라 RAW → 계정 삭제.

## 설계 메모

- **API 호출**: `src/lib/api.ts` 한 곳에서 `/api/v1`만 호출하고, 변경 요청에 `X-CSRF-Token`을 붙입니다. 401이나 보안 토큰 오류를 받으면 로그인 상태를 다시 확인합니다.
- **로그인 상태**: `AuthProvider`가 탭 포커스·다른 탭 알림(BroadcastChannel)으로 계정 변경을 감지해, 다른 탭에서 로그아웃·다른 계정 로그인을 하면 이 탭도 따라 바뀝니다. 로그인 후 이동 주소는 같은 출처만 허용합니다.
- **지구본**: `Globe/GlobeScene.tsx`에 Three.js 코드를 모았습니다(OrbitControls, 해안선은 `world-atlas` Natural Earth 110m → 가까이 확대하면 50m로 교체). 회전·확대가 멈춘 뒤 보이는 범위(bbox)·확대 단계로 핀을 다시 받고, 이전 요청은 취소합니다. 뒤쪽 핀은 숨기고, 화면을 떠나면 WebGL 자원을 해제합니다. 툴팁 문자열은 `textContent`로만 넣습니다.
- **업로드**: 브라우저에서 EXIF(GPS·촬영일)를 읽어 미리 채우고, 읽지 못한 파일(일부 HEIC·RAW)은 서버가 읽도록 맡깁니다(`use_exif_location`·`use_exif_date`). 새 장소 좌표는 공개되므로 촬영 좌표에서 채울 때 약 1km 단위로 반올림합니다. 여러 장은 한 장씩 차례로 올립니다.
- **지도에서 고르기**: Leaflet은 지도를 열 때만 불러옵니다. 장소 검색은 백엔드(`/geocode/*`)를 거치며, 공용 Nominatim 정책상 자동완성 없이 찾기 버튼을 누를 때만 검색합니다.
- **보안 헤더**: 모든 화면에 CSP(외부 스크립트 차단, 이미지는 자기 출처·지도 타일 서버만, `frame-ancestors 'none'`, `object-src 'none'`), `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`. 메일 링크 화면은 `Referrer-Policy: no-referrer`. Next가 인라인 스크립트를 쓰므로 `script-src`에 `'unsafe-inline'`이 남아 있습니다.
- **이미지**: 보호 이미지는 쿠키로 권한을 확인해야 하므로 `next/image` 최적화를 쓰지 않고 `<img>`로 직접 표시합니다.

## 남은 과제

- **개인정보 안내 확정**: `/privacy`는 초안입니다. 운영 정보(`NEXT_PUBLIC_PRIVACY_*`)를 채우고, 사진 GPS(개인위치정보)를 다루므로 위치정보법상 신고·동의 필요 여부를 포함해 법률 검토가 필요합니다.
- **지도 타일 교체**: OpenStreetMap 공용 타일은 소규모 이용만 허용됩니다. 사용자가 늘면 상용·자체 타일 서버로 바꾸세요(설정만 변경).
- **신고 버튼**: 이용자가 사진을 신고하는 화면은 없습니다.
- **CSP nonce**: 인라인 스크립트를 없애려면 모든 화면을 동적 렌더링해야 해서 보류했습니다.
