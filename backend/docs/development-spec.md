# 지구본 사진 기록 서비스 개발 지시서

작성일 2026년 10월 5일 · 버전 1.0 · 구현 전 설계

## 1 목적과 현재 상태

회원가입, 로그인, 사진 업로드, 친구, 공개범위, 장소별 사진, 프로필, 지구본을 모두 포함하는 1차 버전의 개발 기준이다. 현재는 설계 단계이며 실행 가능한 프로젝트를 만든 상태가 아니다. 아래 기술 방식과 수치는 개발 기본안이다. 변경하면 코드와 문서를 함께 갱신한다.

사용 흐름: 가입 → 로그인 → 사진과 장소 등록 → 공개범위 선택 → 지구본에서 장소 선택 → 허용된 사진 보기. 친구는 상호 수락한 관계다.

## 2 기능 범위

| 기능 | 1차 구현 |
| --- | --- |
| 회원 | 이메일·닉네임·비밀번호 가입, 로그인 유지, 로그아웃 |
| 사진 | 사진 한 장 등록, 상세, 설명·장소·촬영일·공개범위 수정, 삭제 |
| 위치 | EXIF GPS 추출, 수동 좌표 지정, 대표 장소 선택·생성 |
| 친구 | 사용자 검색, 요청, 수락, 거절, 취소, 친구 삭제 |
| 공개범위 | PUBLIC / FRIENDS / PRIVATE |
| 지구본 | 회전, 확대, 핀·클러스터, WORLD / FRIENDS / ME |
| 프로필 | 소개, 사진, 기록한 장소, 조회 권한에 맞는 통계 |

좋아요·댓글·DM·알림·AI 평가·여행 컬렉션·연도 필터는 후속 기능이다. 이메일 인증과 비밀번호 재설정은 공개 운영 전 추가한다. 가입 기능 자체는 처음부터 구현한다.

## 3 공통 개발 지시사항

1. 지구본 데모만 만들고 회원·친구·업로드를 누락하지 않는다.
2. 작성자 ID는 인증 사용자로 결정한다. 클라이언트의 user_id를 신뢰하지 않는다.
3. 라우터는 입출력, 서비스는 업무 처리, 모델은 DB, 스키마는 검증을 담당한다.
4. 모든 공개범위 검사는 서버에서 수행한다. 프론트 숨김은 보조 처리다.
5. 비밀번호·토큰·원본·전체 GPS를 로그에 남기지 않는다. .env는 Git에 올리지 않는다.
6. 목록에는 페이지네이션과 상한을 둔다. 로딩·실패·빈 상태를 구분한다.
7. 시간은 UTC로 저장하고 화면에서 사용자 시간대로 표시한다. EXIF 시간대가 없으면 사용자가 확인하도록 한다.
8. 파일과 API 이름을 일관되게 사용하고 README에 실행·확인·미완료 내용을 기록한다.
9. 라이브러리 버전은 실제 구현 시 공식 문서로 호환성을 확인하고 잠금 파일에 고정한다.

## 4 기술과 인증 기본안

| 영역 | 기본안 |
| --- | --- |
| 프론트 | Next.js App Router + TypeScript |
| 서버 | FastAPI, /api/v1 |
| DB | PostgreSQL + SQLAlchemy + Alembic |
| 좌표 | 위도·경도 컬럼, PostGIS는 후속 검토 |
| 지구본 | Three.js 기반 어댑터, 구체 라이브러리는 시제품에서 결정 |
| 이미지 | Pillow, 원본·표시용·썸네일 |
| 저장 | 개발: 비공개 로컬 폴더 / 운영: 비공개 객체 저장소 |
| 인증 | HttpOnly 쿠키 기반 서버 세션 |

이전 JWT 예시는 확정 요구사항이 아니다. 기본안은 서버 세션으로 통일한다. 랜덤 토큰의 해시를 sessions에 저장하고 로그아웃 시 폐기한다. 운영 쿠키에는 Secure·HttpOnly·SameSite를 적용한다. 변경 요청은 CSRF 토큰과 Origin을 검증한다. 가능하면 같은 도메인에서 프론트와 API를 연결한다.

## 5 전체 폴더 구조

```text
photo-globe/
  README.md
  .gitignore
  .env.example
  compose.yaml
  docs/development-spec.md
  frontend/
    package.json
    package-lock.json
    next.config.ts
    tsconfig.json
    .env.example
    src/
      app/
        layout.tsx
        globals.css
        page.tsx
        loading.tsx
        error.tsx
        not-found.tsx
        register/page.tsx
        login/page.tsx
        upload/page.tsx
        friends/page.tsx
        places/[id]/page.tsx
        photos/[id]/page.tsx
        photos/[id]/edit/page.tsx
        users/[username]/page.tsx
        settings/profile/page.tsx
      components/
        Navbar.tsx
        AuthProvider.tsx
        RequireAuth.tsx
        Globe/Globe.tsx
        Globe/GlobeScene.tsx
        Globe/MapFilters.tsx
        Globe/PlacePanel.tsx
        PhotoGrid.tsx
        PhotoCard.tsx
        PhotoUploadForm.tsx
        LocationPicker.tsx
        VisibilitySelector.tsx
        FriendRequestCard.tsx
        ProfileHeader.tsx
        Pagination.tsx
      hooks/useMapPlaces.ts
      lib/api.ts
      lib/auth.ts
      lib/types.ts
      lib/validation.ts
  backend/
    pyproject.toml
    .env.example
    alembic.ini
    migrations/env.py
    migrations/versions/
    app/
      main.py
      core/config.py
      core/database.py
      core/security.py
      dependencies/auth.py
      models/__init__.py
      models/user.py
      models/session.py
      models/friendship.py
      models/place.py
      models/photo.py
      schemas/auth.py
      schemas/user.py
      schemas/friendship.py
      schemas/place.py
      schemas/photo.py
      schemas/map.py
      routers/auth.py
      routers/users.py
      routers/friends.py
      routers/places.py
      routers/photos.py
      routers/map.py
      routers/media.py
      services/auth_service.py
      services/friendship_service.py
      services/place_service.py
      services/photo_service.py
      services/permission_service.py
      services/image_service.py
      services/exif_service.py
      services/storage_service.py
      services/map_service.py
    tests/
      conftest.py
      test_auth.py
      test_friendships.py
      test_photo_permissions.py
      test_upload.py
      test_map.py
```

위 목록은 만들 파일의 설계이며 구현 완료 목록이 아니다.

## 6 루트와 설정 파일

| 파일 | 들어갈 내용 |
| --- | --- |
| README.md | 설치·실행·DB 갱신·테스트·구현 상태 |
| .gitignore | .env·가상환경·node_modules·빌드·사진 저장 폴더 제외 |
| .env.example | 설정 이름과 예시, 실제 비밀 금지 |
| compose.yaml | 개발 PostgreSQL과 영구 볼륨 |
| docs/development-spec.md | 이 문서의 프로젝트 내 사본 |
| frontend/package.json | 개발·빌드·형 검사 명령과 의존성 |
| package-lock.json | 설치 버전 고정 |
| next.config.ts | API 연결과 이미지 설정 |
| tsconfig.json | 타입 검사와 경로 별칭 |
| backend/pyproject.toml | Python 의존성·테스트 설정 |
| alembic.ini / migrations/env.py | DB 연결과 모델 metadata |
| migrations/versions/ | DB 변경 이력, 빈 DB부터 생성 가능 |

설정 항목: DATABASE_URL, SESSION_TTL_SECONDS, COOKIE_SECURE, ALLOWED_ORIGINS, STORAGE_BACKEND, LOCAL_STORAGE_PATH, MAX_UPLOAD_BYTES, MAX_IMAGE_PIXELS, OBJECT_STORAGE_BUCKET. 공개 프론트 환경변수에 DB 비밀번호나 저장소 비밀을 넣지 않는다.

## 7 프론트 파일별 구현 지시

| 파일 | 들어갈 내용 |
| --- | --- |
| app/layout.tsx | 공통 레이아웃, AuthProvider, Navbar, 한국어 설정 |
| app/globals.css | 색·글꼴·여백·폼·모바일 스타일 |
| app/page.tsx | 지구본·검색·필터·선택 장소 상태 |
| loading.tsx / error.tsx / not-found.tsx | 로딩·재시도·없는 페이지, 내부 예외 숨김 |
| register/page.tsx | 이메일·닉네임·비밀번호·확인, 중복 오류, 로그인으로 이동 |
| login/page.tsx | 로그인·실패 표시, 내부 돌아갈 주소만 허용 |
| upload/page.tsx | 인증 요구, 업로드 폼, 완료 후 상세로 이동 |
| friends/page.tsx | 검색·받은 요청·보낸 요청·친구 목록·상태별 작업 |
| places/[id]/page.tsx | 장소 정보·허용 사진·페이지네이션 |
| photos/[id]/page.tsx | 사진·설명·촬영 정보, 소유자 수정·삭제 |
| photos/[id]/edit/page.tsx | 설명·날짜·장소·공개범위 편집 |
| users/[username]/page.tsx | 프로필·사진·장소·친구 관계 |
| settings/profile/page.tsx | 본인 표시명과 소개 수정 |
| Navbar.tsx | 검색·업로드·친구·계정·로그아웃 |
| AuthProvider.tsx | /auth/me로 세션 복원, user/loading 공유 |
| RequireAuth.tsx | 미로그인 안내, 서버 인증은 별도로 유지 |
| Globe/Globe.tsx | 클라이언트 전용 씬 로드와 데이터 전달 |
| Globe/GlobeScene.tsx | 회전·확대·좌표 변환·핀 선택·WebGL 해제 |
| Globe/MapFilters.tsx | WORLD/FRIENDS/ME 전환 |
| Globe/PlacePanel.tsx | 선택 장소·사진·상세 이동, 모바일 하단 패널 |
| PhotoGrid.tsx / PhotoCard.tsx | 썸네일·비율·대체 텍스트·상세 링크 |
| PhotoUploadForm.tsx | 파일·장소·날짜·설명·공개범위·전송·실패 복원 |
| LocationPicker.tsx | 검색·좌표 선택·수동 입력·위치 확인 |
| VisibilitySelector.tsx | 세 범위 설명과 선택, 기본 PRIVATE |
| FriendRequestCard.tsx | 요청·수락·거절·취소·해제 버튼 |
| ProfileHeader.tsx | 공개 소개와 허용된 통계 |
| Pagination.tsx | 다음·이전·로딩 |
| hooks/useMapPlaces.ts | 범위·필터 조회, 호출 간격 조절, 이전 요청 취소 |
| lib/api.ts | fetch, credentials, CSRF, 공통 오류 |
| lib/auth.ts | register/login/logout/me 함수 |
| lib/types.ts | API 응답과 공개범위·필터·관계 타입 |
| lib/validation.ts | 입력 보조 검증, 서버에서도 검증 |

## 8 서버 파일별 구현 지시

| 파일 | 들어갈 내용 |
| --- | --- |
| main.py | 앱 생성·라우터 등록·CORS·health·공통 예외 |
| core/config.py | 환경변수·필수값·범위 검증 |
| core/database.py | Engine·Session·Base·요청별 DB 연결 |
| core/security.py | hash_password, verify_password, 토큰 생성·해시, CSRF |
| dependencies/auth.py | optional_user, require_user, 만료·폐기 세션 검사 |
| models/__init__.py | 모델 등록, Alembic metadata |
| models/user.py | users 모델 |
| models/session.py | sessions 모델 |
| models/friendship.py | friendships 모델·쌍 중복 방지 |
| models/place.py | places 모델·좌표 범위 |
| models/photo.py | photos 모델·소유자·저장 키·공개범위 |
| schemas/auth.py | 가입·로그인 입력과 안전한 응답 |
| schemas/user.py | 공개 프로필·본인 변경 입력 |
| schemas/friendship.py | 요청·관계 상태·목록 응답 |
| schemas/place.py | 장소 생성·검색·상세 |
| schemas/photo.py | 등록·편집·상세·목록 |
| schemas/map.py | mode·bbox·zoom·핀·클러스터 |
| routers/auth.py | 가입·로그인·로그아웃·본인, 쿠키 설정 |
| routers/users.py | 검색·프로필·사진·장소·본인 수정 |
| routers/friends.py | 요청·수락·거절·취소·친구 해제 |
| routers/places.py | 검색·생성·상세·사진 |
| routers/photos.py | multipart 등록·상세·PATCH·DELETE |
| routers/map.py | 필터·영역·확대 수준별 핀 |
| routers/media.py | 권한 확인 후 이미지 제공 |
| services/auth_service.py | 중복 검사·가입·세션 생성과 폐기 |
| services/friendship_service.py | 관계 상태 전환·작업 주체 검사 |
| services/place_service.py | 장소 검색·생성·중복 후보·통계 |
| services/photo_service.py | 등록·편집·삭제·DB와 저장소 정합성 |
| services/permission_service.py | visible_photo_query, can_view_photo, require_owner |
| services/image_service.py | 실제 포맷·크기 검사·방향 보정·리사이즈·EXIF 제거 |
| services/exif_service.py | GPS·날짜·카메라·렌즈 추출, 누락·손상 허용 |
| services/storage_service.py | save/read/delete, 개발·운영 저장소 전환 |
| services/map_service.py | 허용 데이터만 집계·클러스터링 |

권한 코드를 라우터마다 복사하지 않는다. 사진·이미지·장소 통계·프로필·지구본 모두 permission_service를 공유한다. 고정 경로 /users/search, /users/me 등을 동적 /users/{username}보다 먼저 등록한다.

## 9 DB 필드와 제약

| 테이블 | 필드 |
| --- | --- |
| users | id UUID, email, username, display_name, password_hash, bio, created_at, updated_at |
| sessions | id, user_id, token_hash, csrf_token_hash, expires_at, created_at |
| friendships | id, user_low_id, user_high_id, requester_id, status, created_at, accepted_at |
| places | id, name, address?, city?, country_code?, latitude, longitude, created_by?, created_at |
| photos | id, user_id, place_id, original_key, display_key, thumbnail_key, caption, visibility, taken_at?, taken_timezone?, shot_latitude?, shot_longitude?, share_exact_location, camera?, lens?, focal_length?, aperture?, shutter_speed?, iso?, created_at, updated_at |

물음표는 null 허용이다. 이메일·닉네임은 정규화 후 고유해야 한다. 닉네임 기본안은 영숫자와 밑줄 3~30자, 소개 500자, 설명 2000자, 비밀번호 12~128자다. 표시명은 한글을 허용한다. 비밀번호 원문은 저장하지 않는다.

친구 두 ID는 일정한 순서로 정렬하고 페어에 유일 제약을 둔다. 자기 자신 요청은 금지한다. 상태는 PENDING/ACCEPTED이며 거절·취소·해제는 행 삭제다. BLOCKED는 후속 독립 기능이다.

대표 장소 place_id와 실제 촬영 shot 좌표를 분리한다. GPS가 없으면 shot 좌표는 null이다. 이미지에는 영구 공개 URL 대신 비공개 저장 키를 둔다. 촬영일 불명은 등록일로 위장하지 않는다. 위도 −90~90, 경도 −180~180을 검사한다. 장소명만으로 유일 제약을 두지 않는다.

photos의 (user_id, created_at), (place_id, created_at), visibility, 친구 양쪽 ID, sessions의 expires_at에 인덱스를 둔다. 외래키와 삭제 정책을 정하고 Alembic으로 이력을 남긴다.

## 10 API 계약

| 방법 | 경로 | 내용 | 인증 |
| --- | --- | --- | --- |
| POST | /auth/register | 가입 | 불필요 |
| POST | /auth/login | 세션 쿠키·CSRF 발급 | 불필요 |
| POST | /auth/logout | 세션 폐기 | 필수 |
| GET | /auth/me | 본인·CSRF | 필수 |
| GET | /users/search?q= | 닉네임·표시명 검색 | 필수 |
| PATCH | /users/me | 본인 소개 수정 | 필수 |
| GET | /users/{username} | 프로필·허용 통계 | 선택 |
| GET | /users/{username}/photos | 허용 사진 | 선택 |
| GET | /users/{username}/places | 허용 장소 | 선택 |
| POST | /friends/requests | target_user_id로 신청 | 필수 |
| GET | /friends | 수락된 친구 | 필수 |
| GET | /friends/requests?direction= | incoming/outgoing | 필수 |
| POST | /friends/{id}/accept | 수신자 수락 | 필수 |
| POST | /friends/{id}/reject | 수신자 거절 | 필수 |
| DELETE | /friends/{id} | 신청 취소·친구 해제 | 필수 |
| GET | /places?q= | 장소 검색 | 불필요 |
| POST | /places | 이름·좌표로 생성 | 필수 |
| GET | /places/{id} | 정보·허용 사진 수 | 선택 |
| GET | /places/{id}/photos | 허용 사진 목록 | 선택 |
| POST | /photos | multipart 등록 | 필수 |
| GET | /photos/{id} | 상세 | 선택 |
| PATCH | /photos/{id} | 작성자 편집 | 필수 |
| DELETE | /photos/{id} | 작성자 삭제 | 필수 |
| GET | /media/{photo_id}/{variant} | 권한 있는 이미지 | 선택 |
| GET | /map/places?mode=&bbox=&zoom= | 핀·클러스터 | 필터에 따라 |

모든 경로 앞에 /api/v1을 붙인다. 인증 선택도 사진별 권한을 확인한다. ID는 UUID 문자열, 시간은 ISO 8601. 목록은 items와 next_cursor를 반환한다. 기본 limit=24, 최대100. 오류는 code, message, 필요시 field_errors다. 생성201, 조회200, 삭제204, 입력422, 미인증401, 금지403, 없음·사진 조회 불가404, 중복409, 용량413, 포맷415를 사용한다.

사진 등록: file, place_id, caption, visibility, taken_at?, taken_timezone?, shot_latitude?, shot_longitude?, share_exact_location. 카메라 정보는 서버 EXIF 추출을 기본으로 한다. 로그인 오류는 계정 존재와 비밀번호 오류를 같은 안내로 처리하며 가입·로그인 빈도를 제한한다.

## 11 공개범위와 이미지 권한

| 조회자 | PUBLIC | FRIENDS | PRIVATE |
| --- | --- | --- | --- |
| 미로그인 | 허용 | 차단 | 차단 |
| 작성자 | 허용 | 허용 | 허용 |
| 수락된 친구 | 허용 | 허용 | 차단 |
| 신청 중·다른 사람 | 허용 | 차단 | 차단 |

WORLD는 PUBLIC만, FRIENDS는 수락된 친구의 PUBLIC·FRIENDS만, ME는 자신의 모든 사진이다. FRIENDS와 ME는 로그인 필요다. 장소 기본 목록은 조회자에게 허용된 모든 사진이다.

권한 없는 사진은 ID 조회에도404. 썸네일·표시용도 같은 검사를 한다. 원본은 EXIF GPS 노출을 막기 위해 1차에서는 작성자만 내려받는다. 표시용·썸네일 EXIF는 제거한다. static 공개 주소로 보호 사진을 제공하지 않는다.

핀·사진 개수·프로필 통계는 권한 필터 후 계산한다. PRIVATE만 있는 장소는 WORLD에 핀이 없어야 한다. 친구 해제·공개범위 변경 후 다음 요청부터 반영한다. 보호 이미지에는 private, no-store 캐시 정책을 적용한다.

정확한 촬영 좌표는 사진 권한이 있고 share_exact_location=true인 경우만 타인에게 반환한다. false면 대표 장소만 반환한다. 본인은 자신의 좌표를 확인할 수 있다. 친구 수와 명단은 1차에서 본인에게만 보여준다.

## 12 업로드와 저장 처리

사진 선택 → 미리보기·EXIF → GPS 또는 수동 위치 → 대표 장소 → 촬영일 → 설명 → 공개범위 → 저장. 기본 공개범위는 PRIVATE다. 정확한 위치 공개는 별도로 확인한다.

기본 제한: JPEG/PNG/WebP 한 장, 20MB, 최대80MP. HEIC·RAW·다중 업로드는 후속이다. 표시용 긴 변2400px, 썸네일480px, 작은 사진은 확대하지 않는다. 제한은 설정화하고 처리 메모리·시간도 관리한다.

실제 이미지 포맷을 검사하고 EXIF 방향을 보정한다. 손상 EXIF나 GPS 없음도 수동 입력으로 진행할 수 있다. 랜덤 저장 키를 사용하고 사용자의 파일명을 경로로 쓰지 않는다. 저장 실패면 DB를 확정하지 않고, DB 실패면 생성 파일을 청소한다. 삭제 파일 청소 실패는 재시도 가능하게 한다.

무거운 처리가 비동기 서버 이벤트 루프를 막지 않게 한다. 대규모 운영에는 작업 큐와 PROCESSING/READY/FAILED 상태를 추가한다. 전송 중 중복 버튼을 막고 실패 시 작성 내용을 유지한다.

## 13 지구본과 화면 규칙

메인은 지구본 중심이며 상단 검색·등록·친구·프로필, 하단 WORLD/FRIENDS/ME를 둔다. 핀을 누르면 장소명·허용 사진 수·사진 패널을 표시한다. 모바일은 하단 패널로 바꾼다. WebGL 실패 시 장소 목록을 제공한다.

GlobeScene에 라이브러리 코드를 모으고 SSR에서 window를 사용하지 않는다. 화면 이탈 시 WebGL·타이머·이벤트를 해제한다. 서울·교토 등 실제 좌표로 핀 방향을 확인한다. 텍스처·지도 데이터 사용 허가를 확인한다.

멀리서는 국가·도시 또는 지리 그리드, 가까이서는 장소 핀으로 집약한다. 국가 정보 없는 수동 위치도 그리드에 남긴다. 처음에는 소수 핀으로 연결하고 1차 완료 전 데이터 증가와 집약을 검증한다.

bbox는 west,south,east,north이고 west>east는 날짜 변경선을 걸친다. 미지정은 전 지구다. zoom·핀 상한을 검증한다. 회전 중 요청 간격을 제한하고 끝날 때 최신 범위를 조회한다. 뒤쪽 핀은 시각적으로 숨긴다.

클러스터 응답: kind, id, latitude, longitude, photo_count, place_count, label. 장소 응답: kind=place, place_id, name, latitude, longitude, photo_count. 클러스터 클릭은 확대, 장소 클릭은 사진 패널이다.

## 14 친구 상태 전환

관계 없음 → PENDING → ACCEPTED. 보낸 사람은 요청 취소, 받은 사람은 수락·거절, 수락 후 양쪽은 해제가 가능하다. 제삼자는 바꿀 수 없다.

중복·동시 요청은 DB 유일 제약으로 방지한다. 반대 방향 요청은 자동 수락하지 않고 기존 받은 요청을 안내한다. 해제 후 재신청은 새 PENDING이다. 검색과 친구 응답에 이메일을 포함하지 않는다.

## 15 테스트 파일

| 파일 | 확인 내용 |
| --- | --- |
| conftest.py | 분리된 테스트 DB, A/B/C 사용자와 사진·관계 |
| test_auth.py | 가입·중복·해시·실패 인증·만료·로그아웃·CSRF |
| test_friendships.py | 자기 요청·중복·역요청·수신자 제한·제삼자·해제 |
| test_photo_permissions.py | 조회자 네 종류×공개범위, 이미지·편집·삭제 권한 |
| test_upload.py | 정상·위장 확장자·초과 크기·손상 EXIF·실패 정리 |
| test_map.py | 핀·개수 권한, 필터, 날짜 변경선, 응답 상한 |

수동 흐름: 가입 → 로그인 → 업로드 → 지구본 → 장소 → 사진 → 친구 신청 → 다른 계정 수락 → 친구 공개 보기 → 해제 → 접근 차단 → 로그아웃. 데스크톱·모바일, 형 검사·빌드도 확인하고 실제 결과를 기록한다.

## 16 구현 순서와 단계 완료 기준

| 순서 | 작업 | 완료 기준 |
| --- | --- | --- |
| 1 | 구조·설정·DB·마이그레이션 | 빈 환경에서 실행과 DB 생성 |
| 2 | 가입·로그인·세션·화면 | 실제 가입·유지·로그아웃 |
| 3 | 장소·사진·저장·EXIF | PRIVATE 업로드와 본인 조회 |
| 4 | 공개범위·이미지 권한 | 리스트와 이미지 직접 접근 일치 |
| 5 | 친구 화면·API | 요청·수락·해제와 권한 반영 |
| 6 | 상세·편집·삭제·프로필 | DB 데이터와 전체 화면 연결 |
| 7 | 지구본·검색·필터·패널 | 올바른 핀에서 사진으로 이동 |
| 8 | 클러스터·페이지·모바일·오류 | 데이터 증가와 작은 화면 대응 |
| 9 | 통합 검사·문서 갱신 | 기준 확인과 미완료 명시 |

임시 데이터만으로 완료 판정하지 않는다. 이전 10~15일은 추정이며 보장 일정이 아니다.

## 17 최종 수용 기준

- 신규 가입·로그인·로그아웃이 동작한다.
- GPS 없는 사진도 수동 장소로 등록한다.
- 재시작 후 DB와 이미지가 유지된다.
- PUBLIC/FRIENDS/PRIVATE가 목록·직접 링크·이미지·핀·개수·프로필에 일관되게 적용된다.
- 친구 해제와 공개범위 변경 후 다음 요청부터 차단된다.
- 다른 사람이 사진을 수정·삭제할 수 없다.
- 지구본 회전·확대·장소 선택·사진 상세가 연결된다.
- 로딩·오류·빈 상태·모바일 조작이 구현된다.
- 설치 방법·환경 예시·실행한 검사·미완료가 기록된다.

## 18 아직 정하지 않은 항목

서비스명·로고·색상·구체 지구본 라이브러리·장소 검색 제공자·운영 저장소·호스팅은 미확정이다. 로컬 기본안과 교체 가능한 어댑터로 진행한다. 공유 장소의 중복 정리 정책과 운영용 개인정보 안내는 공개 운영 전 확정한다. 기능을 생략하는 이유로 사용하지 않는다.

## 19 개발 담당자에게 전달할 지시문

이 문서에 따라 Next.js, FastAPI, PostgreSQL로 지구본 중심 사진 기록 서비스를 구현한다. 회원가입·로그인·사진·장소·친구·3단계 공개범위·프로필·지구본을 모두 포함한다. 파일 구조를 먼저 만들고 구현 순서대로 연결한다. 서버 공통 권한 검사를 사진·이미지·집계·프로필·지구본에 적용한다. 실제 구현 시 공식 문서로 의존성을 확인하고 권한 테스트와 사용자 흐름을 검증한다. 보고에는 변경 내용·실행법·확인 결과·미완료를 적는다. 화면 데모만으로 전체 서비스가 완료됐다고 보고하지 않는다.
