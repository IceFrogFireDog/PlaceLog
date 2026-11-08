// 브라우저 E2E: 가입·이메일 인증·지도 선택·장소 검색·중복 장소·여러 장/HEIC 업로드·아바타·비밀번호 변경/재설정·친구·지구본 툴팁·수정/삭제
// 빈 DB에서 실행한다. 실행 방법은 프론트 README의 "브라우저 E2E" 참고.
const { chromium } = require("playwright");
const { execFileSync } = require("child_process");
const crypto = require("crypto");
const path = require("path");
const fs = require("fs");

const BASE = process.env.E2E_BASE || "http://localhost:3000";
// 백엔드 저장소 폴더 (메일함 확인·관리자 지정 명령을 여기서 실행). 기본: 이 프론트 폴더 옆의 photo-globe-backend 또는 backend
const BACKEND = process.env.E2E_BACKEND_DIR
  ? path.resolve(process.env.E2E_BACKEND_DIR)
  : [path.resolve(__dirname, "../../photo-globe-backend"), path.resolve(__dirname, "../../backend")]
    .find((p) => fs.existsSync(path.join(p, "app", "tasks.py"))) || path.resolve(__dirname, "../../photo-globe-backend");
if (!fs.existsSync(path.join(BACKEND, "app", "tasks.py"))) {
  throw new Error(`백엔드 폴더를 찾을 수 없습니다: ${BACKEND} (E2E_BACKEND_DIR로 지정)`);
}
const PYTHON = process.env.E2E_PYTHON
  || path.join(BACKEND, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const TMP = path.join(__dirname, ".tmp");
const IMG = path.join(TMP, "img");
const SHOTS = path.join(TMP, "shots");
fs.rmSync(SHOTS, { recursive: true, force: true });
fs.mkdirSync(SHOTS, { recursive: true });
execFileSync(PYTHON, [path.join(__dirname, "make_images.py"), IMG, BACKEND], { cwd: BACKEND, stdio: "inherit" });

/** 개발용 메일함(MAIL_BACKEND=file)에서 가장 최근 링크의 토큰을 꺼내 이 E2E 주소로 바꾼다 */
function mailLink(email, route) {
  const out = execFileSync(PYTHON, ["-m", "app.tasks", "mailbox", "--to", email, "-n", "5"], { cwd: BACKEND }).toString();
  const all = [...out.matchAll(new RegExp(`${route}\\?token=([A-Za-z0-9_\\-]+)`, "g"))];
  if (!all.length) throw new Error(`no ${route} mail for ${email}:\n${out}`);
  return `${BASE}${route}?token=${all[all.length - 1][1]}`;
}

/** RFC 6238 TOTP (인증 앱과 같은 계산) */
function totp(b32, offset = 0) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const bits = [...b32.replace(/[\s=]/g, "").toUpperCase()].map((c) => alphabet.indexOf(c).toString(2).padStart(5, "0")).join("");
  const key = Buffer.from(bits.match(/.{8}/g).map((b) => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000) + offset));
  const mac = crypto.createHmac("sha1", key).update(counter).digest();
  const off = mac[mac.length - 1] & 0x0f;
  return String((mac.readUInt32BE(off) & 0x7fffffff) % 1000000).padStart(6, "0");
}

let failures = 0;
async function step(name, page, fn) {
  try {
    await fn();
    console.log(`  ✓ ${name}`);
  } catch (e) {
    failures++;
    console.log(`  ✗ ${name}\n    ${String(e.message || e).split("\n").slice(0, 6).join("\n    ")}`);
    if (page) await page.screenshot({ path: path.join(SHOTS, `FAIL-${name.replace(/[^\w가-힣]+/g, "_")}.png`), fullPage: true }).catch(() => {});
    throw e;
  }
}
const expectText = async (page, text, timeout = 8000) => { await page.getByText(text, { exact: false }).first().waitFor({ timeout }); };
/** 업로드 직후 사진은 PROCESSING(변환 중) → 변환이 끝날 때까지 기다린다 */
async function waitReady(page, ids, timeout = 30000) {
  const end = Date.now() + timeout;
  for (;;) {
    const st = await Promise.all(ids.map(async (id) => (await (await page.request.get(`${BASE}/api/v1/photos/${id}`)).json()).status));
    if (st.every((x) => x === "READY")) return;
    if (st.includes("FAILED") || Date.now() > end) throw new Error(`photos not ready: ${st}`);
    await page.waitForTimeout(300);
  }
}
const assert = (cond, msg) => { if (!cond) throw new Error(msg); };

async function register(page, u) {
  await page.goto(`${BASE}/register`);
  await page.getByLabel("이메일 (인증 메일을 받을 주소)").fill(u.email);
  await page.getByLabel("닉네임 (영문·숫자·밑줄 3~30자)").fill(u.username);
  await page.getByLabel("표시명 (한글 가능)").fill(u.name);
  await page.getByLabel("비밀번호 (12자 이상)").fill(u.pw);
  await page.getByLabel("비밀번호 확인").fill(u.pw);
}
async function login(page, email, pw) {
  await page.goto(`${BASE}/login`);
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(pw);
  await page.getByRole("button", { name: "로그인" }).click();
  await page.waitForURL(`${BASE}/`);
}
async function verify(page, email) {
  const link = mailLink(email, "/verify-email");
  await page.goto(link);
  await page.waitForFunction(() => !location.search.includes("token="));
  await page.getByRole("button", { name: "이메일 인증하기" }).click();
  await expectText(page, "이메일 인증이 완료되었습니다.");
}

(async () => {
  const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  const ctxA = await browser.newContext({ viewport: { width: 1280, height: 860 }, locale: "ko-KR", timezoneId: "Asia/Seoul" });
  const A = await ctxA.newPage();
  const consoleErrors = [];
  A.on("pageerror", (e) => consoleErrors.push(`pageerror: ${e.message}`));
  // 타일 서버에 못 닿는 환경의 네트워크 오류만 무시 (CSP 위반 등 다른 오류는 모두 실패로 본다)
  A.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) consoleErrors.push(m.text()); });
  const alice = { email: "alice@example.com", username: "alice", name: "앨리스", pw: "alice-password-123" };
  const bob = { email: "bob@example.com", username: "bob_k", name: "밥", pw: "bob-password-12345" };

  console.log("가입·이메일 인증");
  await step("동의 없이 가입하면 막힘", A, async () => {
    await register(A, alice);
    await A.getByRole("button", { name: "가입" }).click();
    await expectText(A, "개인정보 안내에 동의해야 가입할 수 있습니다.");
    assert(A.url().endsWith("/register"), "should stay on register");
  });
  await step("동의 후 가입 → 로그인 화면 안내", A, async () => {
    await A.getByLabel("개인정보 처리 안내를 읽었으며 동의합니다.", { exact: false }).check();
    await A.getByRole("button", { name: "가입" }).click();
    await A.waitForURL(/\/login\?registered=1/);
    await expectText(A, "인증 메일을 보냈습니다");
  });
  await step("로그인 → 인증 안내 띠 + 업로드 막힘", A, async () => {
    await login(A, alice.email, alice.pw);
    await expectText(A, "alice@example.com로 보낸 메일의 링크를 눌러");
    await A.goto(`${BASE}/upload`);
    await expectText(A, "이메일 인증을 마쳐야 사진을 올릴 수 있습니다.");
    assert(await A.getByRole("button", { name: "등록" }).isDisabled(), "submit should be disabled");
  });
  await step("인증 메일 다시 보내기", A, async () => {
    await A.getByRole("button", { name: "인증 메일 다시 보내기" }).click();
    await expectText(A, "인증 메일을 다시 보냈습니다.");
  });
  await step("메일 링크 → 토큰 주소 숨김 → 인증 완료 → 안내 띠 사라짐", A, async () => {
    await verify(A, alice.email);
    await A.goto(`${BASE}/upload`);
    await A.getByLabel("사진 추가", { exact: false }).waitFor();
    assert(!(await A.getByText("로 보낸 메일의 링크를 눌러").count()), "banner should be gone");
  });

  console.log("한 장 업로드: GPS 자동 채움·장소 검색·지도");
  let gyeongbokPlaceId, photo1;
  await step("JPEG 선택 → GPS·촬영일 자동 채움", A, async () => {
    await A.getByLabel("사진 추가", { exact: false }).setInputFiles(path.join(IMG, "gyeongbok.jpg"));
    await expectText(A, "GPS 있음 · 2025-10-03 14:05 (UTC+09:00)");
    assert((await A.getByLabel("촬영 위도").inputValue()).startsWith("37.5796"), "lat prefilled");
    await expectText(A, "사진의 GPS에서 가져온 좌표입니다.");
    assert((await A.getByLabel("촬영 일시").inputValue()) === "2025-10-03T14:05", "date prefilled");
  });
  await step("새 장소: 주소 검색(가짜 Nominatim) → 이름·좌표·도시·국가 채움", A, async () => {
    await A.getByRole("button", { name: "새 장소 만들기" }).click();
    assert((await A.getByLabel("장소 위도").inputValue()) === "37.58", "place lat prefilled & rounded from shot");
    const box = A.getByLabel("주소·장소 이름 검색");
    await box.fill("경복궁");
    await box.press("Enter"); // 바깥 업로드 폼이 제출되면 안 된다
    await A.getByRole("button", { name: /^경복궁/ }).click();
    assert((await A.getByLabel("새 장소 이름").inputValue()) === "경복궁", "name from geocoder");
    assert((await A.getByLabel("장소 위도").inputValue()) === "37.57960", "precise lat from geocoder");
    assert((await A.getByLabel("국가 코드 (선택)").inputValue()) === "KR", "country");
    assert((await A.getByLabel("도시 (선택)").inputValue()) === "서울", "city");
    await A.locator(".map-pin").first().waitFor();
    await A.screenshot({ path: path.join(SHOTS, "01-new-place-map.png"), fullPage: true });
  });
  await step("지도 클릭으로 장소 좌표 변경 + 도시·국가 채우기(역지오코딩)", A, async () => {
    const map = A.locator(".new-place .map-canvas");
    await map.scrollIntoViewIfNeeded();
    const b = await map.boundingBox();
    await A.mouse.click(b.x + b.width / 2 + 40, b.y + b.height / 2 + 30);
    const lat = await A.getByLabel("장소 위도").inputValue();
    assert(lat !== "37.57960" && /^\d+\.\d{5}$/.test(lat), `lat changed by click: ${lat}`);
    await A.getByLabel("도시 (선택)").fill("");
    await A.getByRole("button", { name: "이 좌표로 도시·국가 채우기" }).click();
    await A.waitForFunction(() => document.querySelector('input[maxlength="120"][value="서울"]') !== null || [...document.querySelectorAll("label")].some((l) => l.textContent.startsWith("도시") && l.querySelector("input")?.value === "서울"));
  });
  await step("장소 생성 → 사진 등록 → 상세 화면", A, async () => {
    await A.getByRole("button", { name: "생성" }).click();
    await expectText(A, "대표 장소 · 경복궁");
    await A.getByLabel("설명").fill("가을의 경복궁");
    await A.getByLabel("전체 공개", { exact: false }).check();
    await A.getByRole("button", { name: "등록" }).click();
    await A.waitForURL(/\/photos\/[0-9a-f-]{36}$/);
    photo1 = A.url().split("/").pop();
    await expectText(A, "가을의 경복궁");
    await A.locator(".photo-detail > img").first().waitFor({ timeout: 15000 }); // 변환이 끝나면 화면이 스스로 사진으로 바뀐다
    await waitReady(A, [photo1]);
    const d = await (await A.request.get(`${BASE}/api/v1/photos/${photo1}`)).json();
    gyeongbokPlaceId = d.place.id;
    assert(d.taken_timezone === "+09:00" && d.taken_at.startsWith("2025-10-03T05:05:00"), `taken ${d.taken_at}`);
    assert(Math.abs(d.shot_latitude - 37.57961) < 1e-4, "shot lat saved");
  });

  console.log("여러 장 + HEIC 업로드");
  await step("3장 선택 → 사진별 EXIF 요약, HEIC 미리보기 대체", A, async () => {
    await A.goto(`${BASE}/upload`);
    await A.getByLabel("사진 추가", { exact: false }).setInputFiles([path.join(IMG, "IMG_0001.HEIC"), path.join(IMG, "nogps.png"), path.join(IMG, "tokyo.jpg")]);
    await expectText(A, "GPS 있음 · 2026-05-02 15:20 (UTC+09:00)");
    await expectText(A, "GPS 없음 · 촬영일 없음");
    await expectText(A, "GPS 있음 · 2025-12-24 19:30 (시간대 없음)");
    await A.locator(".thumb.placeholder").first().waitFor({ timeout: 8000 });
    await expectText(A, "GPS가 없는 사진 1장에만 쓰이며");
    await expectText(A, "시간대 정보가 없는 사진 1장의 촬영지 시간대");
  });
  await step("같은 파일 다시 고르면 중복 추가 안 됨, 지원 안 하는 파일은 거절", A, async () => {
    const tmpTxt = path.join(TMP, "note.txt");
    fs.writeFileSync(tmpTxt, "hello");
    await A.getByLabel("사진 추가", { exact: false }).setInputFiles([path.join(IMG, "nogps.png"), tmpTxt]);
    await expectText(A, "note.txt: JPEG·PNG·WebP·HEIC·카메라 RAW만 올릴 수 있습니다.");
    assert((await A.locator(".upload-item").count()) === 3, "still 3 items");
  });
  await step("지도 클릭으로 GPS 없는 사진의 촬영 좌표 지정", A, async () => {
    await A.getByRole("button", { name: "지도에서 촬영 위치 고르기" }).click();
    const map = A.locator("fieldset.location > .map-picker .map-canvas");
    await map.waitFor();
    await A.locator("fieldset.location > .map-picker .leaflet-control-zoom").waitFor();
    await map.scrollIntoViewIfNeeded();
    const b = await map.boundingBox();
    await A.mouse.click(b.x + b.width * 0.5, b.y + b.height * 0.5);
    const lat = Number(await A.getByLabel("촬영 위도").inputValue());
    const lng = Number(await A.getByLabel("촬영 경도").inputValue());
    assert(lat > 30 && lat < 43 && lng > 120 && lng < 135, `shot from map near Korea: ${lat},${lng}`);
    await A.getByRole("button", { name: "지도 닫기" }).click();
  });
  await step("기존 장소 검색으로 선택 + 사진별 설명 + 시간대 지정 → 3장 등록 → 장소 화면", A, async () => {
    await A.getByLabel("기존 장소 검색").fill("경복");
    await A.getByRole("button", { name: /^경복궁/ }).click();
    await A.getByLabel("IMG_0001.HEIC 설명").fill("아이폰 사진");
    await A.getByLabel("시간대 정보가 없는 사진 1장의 촬영지 시간대").selectOption("+09:00");
    await A.getByLabel("친구 공개", { exact: false }).check();
    await A.getByRole("button", { name: "3장 등록" }).click();
    await A.waitForURL(`${BASE}/places/${gyeongbokPlaceId}`, { timeout: 30000 });
    await expectText(A, "볼 수 있는 사진 4장");
  });
  await step("서버 저장값: HEIC는 자기 GPS·날짜, PNG는 지도 좌표, 시간대 없는 사진은 지정한 시간대", A, async () => {
    const list = await (await A.request.get(`${BASE}/api/v1/places/${gyeongbokPlaceId}/photos?limit=10`)).json();
    await waitReady(A, list.items.map((p) => p.id));
    const details = await Promise.all(list.items.map(async (p) => (await A.request.get(`${BASE}/api/v1/photos/${p.id}`)).json()));
    const heic = details.find((d) => d.caption === "아이폰 사진");
    assert(heic && heic.width === 240 && heic.height === 320 && heic.taken_timezone === "+09:00" && Math.abs(heic.shot_latitude - 37.5796) < 1e-3, "heic");
    const png = details.find((d) => d.camera === null && d.width === 600);
    assert(png && png.shot_latitude > 30 && png.taken_at === null, `png ${JSON.stringify(png && [png.shot_latitude, png.taken_at])}`);
    const tokyo = details.find((d) => d.width === 640);
    assert(tokyo && tokyo.taken_timezone === "+09:00" && tokyo.taken_at.startsWith("2025-12-24T10:30:00") && Math.abs(tokyo.shot_longitude - 139.74543) < 1e-3, "tokyo");
    assert(details.filter((d) => d.visibility === "FRIENDS").length === 3, "3 friends-only");
    const disp = await A.request.get(`${BASE}${heic.display_url}`);
    assert(disp.headers()["content-type"] === "image/webp", "heic converted to webp");
  });

  console.log("프로필 사진·비밀번호 변경");
  await step("프로필 사진 올리기 → 상단바·프로필에 표시 → 지우기", A, async () => {
    await A.goto(`${BASE}/settings/profile`);
    await A.locator('input[type="file"]').setInputFiles(path.join(IMG, "avatar.jpg"));
    await expectText(A, "프로필 사진을 바꿨습니다.");
    const src = await A.locator(".navbar img.avatar").getAttribute("src");
    assert(src && src.startsWith(`/api/v1/media/avatars/`), `navbar avatar ${src}`);
    const anonAvatar = await (await browser.newContext()).request.get(`${BASE}${src}`);
    assert(anonAvatar.status() === 200 && anonAvatar.headers()["content-type"] === "image/webp", "avatar public");
    await A.goto(`${BASE}/users/alice`);
    await A.locator(".profile-header img.avatar").waitFor();
    await A.screenshot({ path: path.join(SHOTS, "02-profile-avatar.png") });
    await A.goto(`${BASE}/settings/profile`);
    A.once("dialog", (d) => d.accept());
    await A.getByRole("button", { name: "사진 지우기" }).click();
    await expectText(A, "프로필 사진을 지웠습니다.");
    await A.locator(".navbar .avatar-empty").waitFor();
  });
  const ctxA2 = await browser.newContext();
  const A2 = await ctxA2.newPage();
  await step("비밀번호 변경: 틀린 현재 비밀번호 거절 → 변경 후 다른 기기 로그아웃", A, async () => {
    await login(A2, alice.email, alice.pw);
    await A.getByLabel("현재 비밀번호").fill("wrong-password-xx");
    await A.getByLabel("새 비밀번호 (12자 이상)").fill("alice-new-password-1");
    await A.getByLabel("새 비밀번호 확인").fill("alice-new-password-1");
    await A.getByRole("button", { name: "비밀번호 바꾸기" }).click();
    await expectText(A, "현재 비밀번호", 4000);
    await A.getByLabel("현재 비밀번호").fill(alice.pw);
    await A.getByRole("button", { name: "비밀번호 바꾸기" }).click();
    await expectText(A, "다른 기기의 로그인은 해제되었습니다.");
    alice.pw = "alice-new-password-1";
    assert((await A.request.get(`${BASE}/api/v1/auth/me`)).status() === 200, "current session kept");
    assert((await A2.request.get(`${BASE}/api/v1/auth/me`)).status() === 401, "other device logged out");
  });

  console.log("두 번째 사용자: 인증 전 제한·중복 장소·친구");
  const ctxB = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true, locale: "ko-KR" });
  const B = await ctxB.newPage();
  B.on("pageerror", (e) => consoleErrors.push(`B pageerror: ${e.message}`));
  B.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) consoleErrors.push(`B: ${m.text()}`); });
  await step("밥 가입·로그인(모바일), 인증 전 친구 요청은 안내 메시지", B, async () => {
    await register(B, bob);
    await B.getByLabel("개인정보 처리 안내를 읽었으며 동의합니다.", { exact: false }).check();
    await B.getByRole("button", { name: "가입" }).click();
    await B.waitForURL(/\/login/);
    await login(B, bob.email, bob.pw);
    await B.goto(`${BASE}/users/alice`);
    await B.getByRole("button", { name: "친구 요청" }).click();
    await expectText(B, "이메일 인증을 마친 뒤 이용할 수 있습니다.");
  });
  await step("밥 인증 → 같은 이름 근처 장소 만들면 중복 안내 → 기존 장소 사용", B, async () => {
    await verify(B, bob.email);
    await B.goto(`${BASE}/upload`);
    await B.getByLabel("사진 추가", { exact: false }).setInputFiles(path.join(IMG, "nogps.png"));
    await B.getByRole("button", { name: "새 장소 만들기" }).click();
    await B.getByLabel("새 장소 이름").fill("경복궁 ");
    await B.getByLabel("장소 위도").fill("37.5797");
    await B.getByLabel("장소 경도").fill("126.9771");
    await B.getByRole("button", { name: "생성" }).click();
    await expectText(B, "근처에 같은 이름의 장소");
    await B.screenshot({ path: path.join(SHOTS, "03-duplicate-mobile.png"), fullPage: true });
    await B.getByRole("button", { name: "이 장소 사용" }).click();
    await expectText(B, "대표 장소 · 경복궁");
  });
  await step("밥 → 앨리스 친구 요청, 앨리스 수락, 친구 공개 사진 보임", B, async () => {
    await B.goto(`${BASE}/users/alice`);
    await B.getByRole("button", { name: "친구 요청" }).click();
    await B.getByRole("button", { name: "요청 취소" }).waitFor();
    const before = await (await B.request.get(`${BASE}/api/v1/places/${gyeongbokPlaceId}`)).json();
    assert(before.photo_count === 1, `bob sees only public before: ${before.photo_count}`);
    await A.goto(`${BASE}/friends`);
    await A.getByRole("button", { name: "수락" }).click();
    await A.getByRole("button", { name: "친구 해제" }).waitFor();
    const after = await (await B.request.get(`${BASE}/api/v1/places/${gyeongbokPlaceId}`)).json();
    assert(after.photo_count === 4, `bob sees friends photos: ${after.photo_count}`);
  });

  console.log("비밀번호 재설정");
  await step("로그아웃 → 비밀번호 찾기 → 메일 링크 → 새 비밀번호 → 로그인", A, async () => {
    await A.getByRole("button", { name: "로그아웃" }).click();
    await A.waitForURL(`${BASE}/`);
    await A.goto(`${BASE}/login`);
    await A.getByRole("link", { name: "비밀번호를 잊으셨나요?" }).click();
    await A.waitForURL(`${BASE}/forgot-password`);
    await A.getByLabel("이메일").fill(alice.email);
    await A.getByRole("button", { name: "재설정 링크 받기" }).click();
    await expectText(A, "가입된 이메일이라면 비밀번호 재설정 링크를 보냈습니다.");
    await A.goto(mailLink(alice.email, "/reset-password"));
    await A.waitForFunction(() => !location.search.includes("token="));
    await A.getByLabel("새 비밀번호 (12자 이상)").fill("alice-reset-pass-99");
    await A.getByLabel("새 비밀번호 확인").fill("alice-reset-pass-99");
    await A.getByRole("button", { name: "비밀번호 바꾸기" }).click();
    await A.waitForURL(/\/login\?reset=1/);
    await expectText(A, "새 비밀번호로 로그인해 주세요.");
    await login(A, alice.email, "alice-reset-pass-99");
    alice.pw = "alice-reset-pass-99";
  });

  console.log("2단계 인증");
  await step("2단계 인증 켜기(QR·키) → 복구 코드 → 다시 로그인할 때 인증 앱 코드 → 복구 코드로 끄기", A, async () => {
    await A.goto(`${BASE}/settings/profile`);
    const sec = A.locator(".two-factor");
    await sec.getByRole("button", { name: "2단계 인증 켜기" }).click();
    await sec.getByLabel("비밀번호 확인").fill(alice.pw);
    await sec.getByRole("button", { name: "다음" }).click();
    await sec.locator("img.qr").waitFor();
    const secret = (await sec.locator("code.secret").textContent()).replace(/\s/g, "");
    await sec.getByLabel("2. 앱에 표시된 6자리 코드").fill(totp(secret));
    await sec.getByRole("button", { name: "켜기" }).click();
    await sec.locator(".recovery-codes code").first().waitFor();
    const codes = await sec.locator(".recovery-codes code").allTextContents();
    assert(codes.length === 10 && /^[a-z2-9]{4}-[a-z2-9]{4}$/.test(codes[0]), `codes ${codes}`);
    await A.screenshot({ path: path.join(SHOTS, "05-two-factor.png"), fullPage: true });
    await sec.getByRole("button", { name: "보관했습니다" }).click();

    await A.getByRole("button", { name: "로그아웃" }).click();
    await A.waitForURL(`${BASE}/`);
    await A.goto(`${BASE}/login`);
    await A.getByLabel("이메일").fill(alice.email);
    await A.getByLabel("비밀번호").fill(alice.pw);
    await A.getByRole("button", { name: "로그인" }).click();
    await A.getByLabel("2단계 인증 코드").fill(totp(secret, 1)); // 켤 때 쓴 코드는 재사용 불가 → 다음 30초 코드
    await A.getByRole("button", { name: "로그인" }).click();
    await A.waitForURL(`${BASE}/`);

    await A.goto(`${BASE}/settings/profile`);
    await sec.getByLabel("비밀번호", { exact: true }).fill(alice.pw);
    await sec.getByLabel("인증 코드 또는 복구 코드").fill(codes[0]);
    await sec.getByRole("button", { name: "2단계 인증 끄기" }).click();
    await expectText(A, "2단계 인증을 껐습니다.");
  });

  console.log("관리자");
  await step("관리자 지정(서버 명령) → 관리 화면 통계·사용자 검색 → 밥 정지(즉시 로그아웃) → 해제", A, async () => {
    execFileSync(PYTHON, ["-m", "app.tasks", "make-admin", alice.email], { cwd: BACKEND });
    await A.goto(`${BASE}/admin`);
    await A.getByRole("link", { name: "관리", exact: true }).waitFor();
    await A.locator(".stat-grid li").first().waitFor();
    await A.getByLabel("사용자 검색").fill("bob");
    await A.getByRole("button", { name: "검색" }).click();
    const row = A.locator(".admin-table tbody tr", { hasText: "@bob_k" });
    await row.waitFor();
    await A.screenshot({ path: path.join(SHOTS, "06-admin.png"), fullPage: true });
    A.once("dialog", (d) => d.accept());
    await row.getByRole("button", { name: "정지", exact: true }).click();
    await row.getByRole("button", { name: "정지 해제", exact: true }).waitFor();
    assert((await B.request.get(`${BASE}/api/v1/auth/me`)).status() === 401, "suspended user logged out");
    A.once("dialog", (d) => d.accept());
    await row.getByRole("button", { name: "정지 해제", exact: true }).click();
    await row.getByRole("button", { name: "정지", exact: true }).waitFor();
    await login(B, bob.email, bob.pw); // 정지가 풀리면 다시 로그인 가능
  });

  console.log("지구본 툴팁·상세 해안선·개인정보 안내");
  await step("검색으로 경복궁 이동 → 핀에 마우스 올리면 툴팁, 확대 시 1:50m 해안선 로드", A, async () => {
    await A.goto(`${BASE}/?q=${encodeURIComponent("경복궁")}`);
    await A.locator(".globe-canvas canvas").waitFor({ timeout: 15000 });
    const before = await A.evaluate(() => performance.getEntriesByType("resource").length);
    await A.locator(".search-results").getByRole("button", { name: "경복궁" }).click();
    await A.waitForTimeout(3500); // 카메라 이동 애니메이션
    const c = await A.locator(".globe-canvas").boundingBox();
    await A.mouse.move(c.x + c.width / 2 - 3, c.y + c.height / 2 - 3);
    await A.mouse.move(c.x + c.width / 2, c.y + c.height / 2);
    const tip = A.locator(".globe-tooltip");
    await tip.waitFor({ state: "visible", timeout: 5000 });
    const text = await tip.textContent();
    assert(/^경복궁 · 사진 1장$/.test(text), `tooltip (전체 지도는 전체 공개 사진만 셈): ${text}`);
    await A.screenshot({ path: path.join(SHOTS, "04-globe-tooltip.png") });
    const big = await A.evaluate((n) => performance.getEntriesByType("resource").slice(n).filter((r) => r.decodedBodySize > 300000).map((r) => r.name), before);
    assert(big.length >= 1, "50m coastline chunk loaded on zoom");
    await A.mouse.move(c.x + 10, c.y + 10);
    await tip.waitFor({ state: "hidden", timeout: 3000 });
  });
  await step("개인정보 안내 화면과 바닥글 링크", A, async () => {
    assert((await A.locator(".site-footer").count()) === 0, "no footer on globe");
    await A.goto(`${BASE}/friends`);
    await A.locator(".site-footer").getByRole("link", { name: "개인정보 처리 안내" }).click();
    await A.waitForURL(`${BASE}/privacy`);
    await expectText(A, "3. 위치정보 처리");
  });

  console.log("사진 수정·삭제");
  await step("수정: 설명 변경·촬영 좌표 지우기 → 저장 → 삭제", A, async () => {
    await A.goto(`${BASE}/photos/${photo1}`);
    await A.getByRole("link", { name: "수정" }).click();
    await A.waitForURL(`${BASE}/photos/${photo1}/edit`);
    await A.getByLabel("설명").fill("수정한 설명");
    await A.getByRole("button", { name: "촬영 좌표 지우기" }).click();
    await A.getByRole("button", { name: "저장" }).click();
    await A.waitForURL(`${BASE}/photos/${photo1}`);
    await expectText(A, "수정한 설명");
    const d = await (await A.request.get(`${BASE}/api/v1/photos/${photo1}`)).json();
    assert(d.caption === "수정한 설명" && d.shot_latitude === null, "edited");
    A.once("dialog", (dlg) => dlg.accept());
    await A.getByRole("button", { name: "삭제" }).click();
    await A.waitForURL(`${BASE}/users/alice`);
    assert((await A.request.get(`${BASE}/api/v1/photos/${photo1}`)).status() === 404, "deleted");
  });

  await step("이미지 데이터가 잘린 파일 → 변환 실패 안내와 다시 시도 버튼(작성자만) → 삭제", A, async () => {
    await A.goto(`${BASE}/upload`);
    await A.getByLabel("사진 추가", { exact: false }).setInputFiles(path.join(IMG, "broken.jpg"));
    await A.getByLabel("기존 장소 검색").fill("경복");
    await A.getByRole("button", { name: /^경복궁/ }).click();
    await A.getByRole("button", { name: "등록" }).click();
    await A.waitForURL(/\/photos\/[0-9a-f-]{36}$/);
    await expectText(A, "사진을 변환하지 못했습니다.", 15000);
    await A.getByRole("button", { name: "다시 시도" }).waitFor();
    A.once("dialog", (d) => d.accept());
    await A.getByRole("button", { name: "삭제" }).click();
    await A.waitForURL(`${BASE}/users/alice`);
  });

  await step("카메라 RAW(DNG) 한 장: 브라우저가 GPS·촬영일을 읽고, 서버가 세로 사진으로 변환", A, async () => {
    await A.goto(`${BASE}/upload`);
    await A.getByLabel("사진 추가", { exact: false }).setInputFiles(path.join(IMG, "DSC_0001.DNG"));
    await expectText(A, "GPS 있음 · 2025-08-15 09:30 (UTC+09:00)");
    await A.locator(".thumb.placeholder").getByText("RAW", { exact: false }).waitFor();
    await A.getByLabel("기존 장소 검색").fill("경복");
    await A.getByRole("button", { name: /^경복궁/ }).click();
    await A.getByRole("button", { name: "등록" }).click();
    await A.waitForURL(/\/photos\/[0-9a-f-]{36}$/);
    const id = A.url().split("/").pop();
    await waitReady(A, [id]);
    await A.locator(".photo-detail > img").waitFor({ timeout: 15000 });
    const d = await (await A.request.get(`${BASE}/api/v1/photos/${id}`)).json();
    assert(d.width < d.height && Math.abs(d.shot_latitude - 37.5445) < 1e-3 && d.taken_timezone === "+09:00", `raw detail ${JSON.stringify([d.width, d.height, d.shot_latitude])}`);
  });

  console.log("계정 삭제");
  await step("밥 계정 삭제(비밀번호 확인) → 로그인 화면 안내 → 프로필 사라짐·다시 로그인 불가", B, async () => {
    await B.goto(`${BASE}/settings/profile`);
    const zone = B.locator(".danger-zone");
    await zone.getByRole("button", { name: "계정 삭제" }).click();
    await expectText(B, "안내를 읽고 확인란에 체크해 주세요.");
    await zone.getByLabel("비밀번호 확인").fill(bob.pw);
    await zone.getByLabel("위 내용을 이해했으며 계정을 삭제합니다.").check();
    B.once("dialog", (d) => d.accept());
    await zone.getByRole("button", { name: "계정 삭제" }).click();
    await B.waitForURL(/\/login\?deleted=1/);
    await expectText(B, "계정을 삭제했습니다.");
    assert((await B.request.get(`${BASE}/api/v1/users/${bob.username}`)).status() === 404, "profile gone");
    const r = await B.request.post(`${BASE}/api/v1/auth/login`, { data: { email: bob.email, password: bob.pw }, headers: { Origin: BASE } });
    assert(r.status() === 401, `login after delete: ${r.status()}`);
  });

  console.log(consoleErrors.length ? `콘솔 오류 ${consoleErrors.length}건:\n  ${consoleErrors.slice(0, 10).join("\n  ")}` : "콘솔 오류 없음");
  await browser.close();
  console.log(failures ? `실패 ${failures}` : "E2E 모두 통과");
  process.exit(failures ? 1 : 0);
})().catch(async (e) => { console.error("중단:", e.message.split("\n")[0]); process.exit(1); });
