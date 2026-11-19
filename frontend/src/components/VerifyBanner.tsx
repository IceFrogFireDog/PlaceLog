"use client";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { errorMessage } from "@/lib/api";
import { resendVerification } from "@/lib/auth";
import { useAuth } from "./AuthProvider";

/** 이메일 인증 전인 사용자에게 모든 화면 위쪽에 안내를 띄운다. 인증 전에는 사진 등록·장소 생성·친구 요청이 막힌다. */
export function VerifyBanner() {
  const { user } = useAuth();
  const path = usePathname();
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!user || user.email_verified !== false || path === "/verify-email") return null; // 인증 기능이 없는 백엔드는 필드가 없음

  async function onResend() {
    setBusy(true); setMsg(null);
    try { setMsg((await resendVerification()).message); } catch (e) { setMsg(errorMessage(e)); } finally { setBusy(false); }
  }

  return (
    <div className="verify-banner" role="status">
      <span><strong>{user.email}</strong>로 보낸 메일의 링크를 눌러 이메일 인증을 마쳐 주세요. 인증 전에는 사진 등록·장소 만들기·친구 요청을 할 수 없습니다.</span>
      <button className="btn" onClick={onResend} disabled={busy}>{busy ? "보내는 중…" : "인증 메일 다시 보내기"}</button>
      {msg && <span className="muted">{msg}</span>}
    </div>
  );
}
