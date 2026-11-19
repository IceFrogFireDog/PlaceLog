"use client";
import Link from "next/link";
import { useState } from "react";
import { errorMessage } from "@/lib/api";
import { forgotPassword } from "@/lib/auth";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try { setSent((await forgotPassword(email.trim())).message); } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  }

  return (
    <form className="card form narrow" onSubmit={onSubmit}>
      <h1>비밀번호 찾기</h1>
      {sent ? (
        <>
          <p className="ok" role="status">{sent}</p>
          <p className="hint">메일이 오지 않으면 스팸함을 확인하거나 몇 분 뒤 다시 요청해 주세요. 링크는 1시간 동안 한 번만 쓸 수 있습니다.</p>
        </>
      ) : (
        <>
          <p className="muted">가입한 이메일을 입력하면 비밀번호를 다시 정할 수 있는 링크를 보내 드립니다.</p>
          <label>이메일<input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
          {err && <p className="error" role="alert">{err}</p>}
          <button className="btn primary" disabled={busy}>{busy ? "보내는 중…" : "재설정 링크 받기"}</button>
        </>
      )}
      <p className="muted"><Link href="/login">로그인으로 돌아가기</Link></p>
    </form>
  );
}
