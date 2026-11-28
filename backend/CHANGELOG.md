# 변경 내역

백엔드 변경 사항입니다 (최근 버전이 위).

## 0.4.0

### 추가
- 사진 변환 작업 큐: 업로드는 원본만 저장하고 바로 응답(`status: PROCESSING`), 표시용·썸네일은 응답 뒤 변환해 `READY`/`FAILED`. `POST /photos/{id}/retry`, 작업자 `python -m app.tasks worker`·`process-pending`
- 카메라 RAW 업로드(DNG·CR2·NEF·ARW 등, `MAX_RAW_UPLOAD_BYTES` 80MB): 내장 미리보기 사용·절반 크기 현상, TIFF 구조 RAW의 EXIF
- 2단계 인증: `/auth/2fa/*`, 로그인 `otp`, 복구 코드, 운영자 해제 명령 `disable-2fa`
- 관리자 API `/admin/*`(통계·사용자 검색·이용 정지·사진 삭제·중복 장소 합치기), `make-admin` 명령
- 계정 탈퇴 `DELETE /users/me`
- API 보안 헤더(CSP·nosniff·DENY·no-referrer)
- 배포: `Dockerfile`, `compose.prod.yaml`(Caddy·DB·캐시·백엔드·작업자·프론트), `deploy/Caddyfile`, `deploy/check.sh`, CI에 Docker 이미지 빌드

### 바뀜
- 변환 중·실패 사진은 작성자에게만 보임(목록·지도·장소 노출 모두 `READY`만). 변환 전 표시용·썸네일 요청은 409 `PHOTO_PROCESSING`/`PHOTO_FAILED`
- 지구본 첫 화면 캐시(`MAP_CACHE_SECONDS`), 전체 지도 부분 인덱스
- 정지된 계정은 로그인(403 `ACCOUNT_SUSPENDED`)과 남은 세션 모두 차단
- 사용자 정보에 `two_factor_enabled`·`is_admin`, 사진에 `status`·`processing_error`(작성자만)

### DB
- `0003` 사진 변환 상태·지구본 인덱스(기존 사진은 `READY`), `0004` 2단계 인증·복구 코드, `0005` 관리자·이용 정지

### 테스트
- 120개 (변환 큐·RAW·2단계 인증·관리자·탈퇴·보안 헤더·캐시 추가)

## 0.3.0

### 추가
- 이메일 인증(`/auth/email/verify`·`/resend`), 인증 전에는 사진 등록·장소 생성·친구 요청 차단(`EMAIL_VERIFICATION_REQUIRED`)
- 비밀번호 찾기·재설정·변경(`/auth/password/forgot`·`/reset`·`/change`), 메일 발송(`MAIL_BACKEND` file/smtp/none)
- 가입 시 개인정보 안내 동의(`agree_privacy`) 필수
- 프로필 사진(`PUT|DELETE /users/me/avatar`, `GET /media/avatars/…`)
- 아이폰 HEIC 업로드, 업로드 `use_exif_date`
- 장소 검색(`/geocode/search`·`/reverse`, Nominatim·카카오)
- 장소 중복 정책: 같은 이름 200m 이내면 409 `DUPLICATE_PLACE`(`force`로 강제 생성)
- S3 호환 저장소(`STORAGE_BACKEND=object`), Redis 빈도 제한(`RATE_LIMIT_BACKEND=redis`)
- 운영 명령 `python -m app.tasks cleanup`·`duplicates`·`merge-places`·`mailbox`

### 바뀜
- 사용자 정보에 `email_verified`·`avatar_url`

### DB
- `0002` 이메일 토큰·인증 시각·동의 시각·프로필 사진(기존 계정은 인증된 것으로 처리)

### 테스트
- 91개 (이메일 인증·HEIC·프로필 사진·장소 검색·중복 정책·S3·정리 작업·Redis 추가)

## 0.2.0

### 추가
- 장소: 만들기(200m 이내 기존 장소 후보 안내)·이름·도시 검색·상세·장소별 사진
- 사진: 업로드(JPEG·PNG·WebP) — 실제 형식·해상도 검사, EXIF(GPS·촬영일·시간대·카메라) 자동 채움, 표시용·썸네일 WebP(EXIF 제거), 수정·삭제
- 공개 범위 권한(`permission_service`): 사진·이미지·장소·프로필·지구본에 같은 규칙
- 이미지 전달 `/media/{id}/thumbnail|display|original`(원본은 작성자만)
- 지구본 `/map/places`: 전체/친구/나 모드, 범위·확대별 핀·클러스터, 날짜 변경선
- 프로필에 사진·장소 수, `/users/{username}/photos`·`/places`

### 테스트
- 59개 (업로드·권한 교차 확인·지구본·이상 입력·장소 후보 추가)

## 0.1.0

### 추가
- 프로젝트 구조, 설정, PostgreSQL 연결, 공통 오류·페이지 형식
- DB 설계와 마이그레이션 `0001`(사용자·세션·친구·장소·사진)
- 가입·로그인·로그아웃·내 정보(HttpOnly 쿠키 세션, CSRF, Origin 검사, 빈도 제한)
- 프로필 조회·수정, 사용자 검색
- 친구 요청·수락·거절·취소·해제·목록
- 개발용 DB(`compose.yaml`), 해시 잠금 파일, GitHub Actions CI

### 테스트
- 20개
