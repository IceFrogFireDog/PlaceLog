"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { useUrlToken } from "@/hooks/useUrlToken";
import { ApiError, errorMessage } from "@/lib/api";
import { resetPassword } from "@/lib/auth";
import { validatePassword } from "@/lib/validation";

function Reset() {
  const token = useUrlToken();
  const router = useRouter();
  const { setUser } = useAuth();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const local = validatePassword(password, confirm);
    setErrs(local); setErr(null);
    if (Object.keys(local).length || !token) return;
    setBusy(true);
    try {
      await resetPassword(token, password);
      setUser(null); // 서버가 모든 기기의 로그인을 해제했다
      router.replace("/login?reset=1");
    } catch (e) {
      if (e instanceof ApiError && e.code === "TOKEN_INVALID") setExpired(true);
      else if (e instanceof ApiError) { setErrs(e.fieldErrors); setErr(e.message); }
      else setErr(errorMessage(e));
      setBusy(false);
    }
  }

  if (!token || expired) {
    return (
      <div className="card narrow stack">
        <h1>비밀번호 재설정</h1>
        <p className="error">{token ? "링크가 만료되었거나 이미 사용되었습니다." : "링크가 올바르지 않습니다."}</p>
        <p><Link className="btn" href="/forgot-password">재설정 링크 다시 받기</Link></p>
      </div>
    );
  }
  return (
    <form className="card form narrow" onSubmit={onSubmit}>
      <h1>새 비밀번호 정하기</h1>
      <label>새 비밀번호 (12자 이상)<input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} aria-invalid={!!errs.password} />
        {errs.password && <span className="error">{errs.password}</span>}</label>
      <label>새 비밀번호 확인<input type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} aria-invalid={!!errs.confirm} />
        {errs.confirm && <span className="error">{errs.confirm}</span>}</label>
      {err && <p className="error" role="alert">{err}</p>}
      <button className="btn primary" disabled={busy}>{busy ? "바꾸는 중…" : "비밀번호 바꾸기"}</button>
      <p className="hint">바꾸면 모든 기기에서 로그아웃됩니다.</p>
    </form>
  );
}

export default function ResetPasswordPage() {
  return <Suspense fallback={null}><Reset /></Suspense>;
}
