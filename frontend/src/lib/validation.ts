// 입력 보조 검증. 최종 검증은 서버가 수행한다.
export const USERNAME_RE = /^[A-Za-z0-9_]{3,30}$/;

export function validatePassword(password: string, confirm: string): Record<string, string> {
  const e: Record<string, string> = {};
  if (password.length < 12 || password.length > 128) e.password = "비밀번호는 12~128자";
  if (password !== confirm) e.confirm = "비밀번호가 일치하지 않습니다.";
  return e;
}

export function validateRegister(v: { email: string; username: string; display_name: string; password: string; confirm: string; agree_privacy: boolean }) {
  const e: Record<string, string> = validatePassword(v.password, v.confirm);
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.email)) e.email = "이메일 형식을 확인해 주세요.";
  if (!USERNAME_RE.test(v.username)) e.username = "영문·숫자·밑줄 3~30자";
  if (!v.display_name.trim() || v.display_name.length > 50) e.display_name = "1~50자";
  if (!v.agree_privacy) e.agree_privacy = "개인정보 안내에 동의해야 가입할 수 있습니다.";
  return e;
}

export function validLatLng(lat: number, lng: number) {
  return Number.isFinite(lat) && Number.isFinite(lng) && lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180;
}

/** 브라우저 현재 시간대 오프셋 "+09:00" */
export function localOffset(d = new Date()): string {
  const m = -d.getTimezoneOffset();
  const sign = m >= 0 ? "+" : "-";
  const a = Math.abs(m);
  return `${sign}${String(Math.floor(a / 60)).padStart(2, "0")}:${String(a % 60).padStart(2, "0")}`;
}

export const OFFSETS = Array.from({ length: 27 }, (_, i) => i - 12).map((h) => `${h >= 0 ? "+" : "-"}${String(Math.abs(h)).padStart(2, "0")}:00`)
  .concat(["+05:30", "+05:45", "+09:30", "+03:30"]).sort();

export function formatDate(iso: string | null, tz?: string | null): string {
  if (!iso) return "촬영일 미상";
  const d = new Date(iso);
  const mine = d.toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" });
  return tz ? `${mine} (내 시간대 기준 · 촬영지 UTC${tz})` : mine;
}
