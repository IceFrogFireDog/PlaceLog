# 변경 내역

백엔드 변경 사항입니다 (최근 버전이 위).

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
