import { api, setCsrfToken } from "./api";
import type { Me, Message, UserBrief } from "./types";

export const register = (data: { email: string; username: string; display_name: string; password: string; agree_privacy: boolean }) =>
  api<UserBrief>("/auth/register", { method: "POST", json: data });

export const verifyEmail = (token: string) => api<Message>("/auth/email/verify", { method: "POST", json: { token } });
export const resendVerification = () => api<Message>("/auth/email/resend", { method: "POST" });
export const forgotPassword = (email: string) => api<Message>("/auth/password/forgot", { method: "POST", json: { email } });
export const resetPassword = (token: string, password: string) => api<Message>("/auth/password/reset", { method: "POST", json: { token, password } });
export const changePassword = (current_password: string, new_password: string) =>
  api<Message>("/auth/password/change", { method: "POST", json: { current_password, new_password } });

/** otp: 2단계 인증이 켜진 계정의 인증 앱 코드 또는 복구 코드 (없으면 서버가 OTP_REQUIRED로 묻는다) */
export async function login(email: string, password: string, otp?: string): Promise<Me> {
  const me = await api<Me>("/auth/login", { method: "POST", json: { email, password, ...(otp ? { otp } : {}) } });
  setCsrfToken(me.csrf_token);
  return me;
}

export async function logout(): Promise<void> {
  await api<void>("/auth/logout", { method: "POST" });
  setCsrfToken(null);
}

export async function fetchMe(): Promise<Me | null> {
  try {
    const me = await api<Me>("/auth/me");
    setCsrfToken(me.csrf_token);
    return me;
  } catch {
    setCsrfToken(null);
    return null;
  }
}

/**
 * 로그인 후 돌아갈 주소: 같은 사이트 내부 경로만 허용 (오픈 리다이렉트 방지).
 * 브라우저는 URL의 탭·줄바꿈을 지우므로("/\t/evil.com" → //evil.com) 문자열 검사 대신 실제로 해석해 출처를 비교한다.
 */
export function safeNext(next: string | null, origin = typeof window !== "undefined" ? window.location.origin : "http://localhost"): string {
  if (!next || !next.startsWith("/")) return "/";
  try {
    const u = new URL(next, origin);
    if (u.origin !== origin) return "/";
    return u.pathname + u.search + u.hash;
  } catch {
    return "/";
  }
}

// ---- 2단계 인증 ----
export const twoFactorStatus = () => api<{ enabled: boolean; recovery_codes_left: number }>("/auth/2fa");
export const twoFactorSetup = (password: string) => api<{ secret: string; otpauth_uri: string }>("/auth/2fa/setup", { method: "POST", json: { password } });
export const twoFactorEnable = (code: string) => api<{ recovery_codes: string[] }>("/auth/2fa/enable", { method: "POST", json: { code } });
export const twoFactorDisable = (password: string, code: string) => api<Message>("/auth/2fa/disable", { method: "POST", json: { password, code } });
export const twoFactorNewCodes = (password: string, code: string) =>
  api<{ recovery_codes: string[] }>("/auth/2fa/recovery-codes", { method: "POST", json: { password, code } });
