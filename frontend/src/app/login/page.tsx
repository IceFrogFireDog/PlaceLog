"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { ApiError, errorMessage } from "@/lib/api";
import { login, safeNext } from "@/lib/auth";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { user, loading, setUser } = useAuth();
  const next = safeNext(params.get("next"));
  useEffect(() => { if (!loading && user) router.replace(next); }, [loading, user, next, router]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [needOtp, setNeedOtp] = useState(false); // 2단계 인증이 켜진 계정이면 코드를 한 번 더 묻는다
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      setUser(await login(email, password, needOtp ? otp.trim() : undefined));
      router.push(next);
    } catch (e) {
      if (e instanceof ApiError && e.code === "OTP_REQUIRED") { setNeedOtp(true); setErr(null); }
      else setErr(errorMessage(e));
    } finally { setBusy(false); }
  }

  return (
    <form className="card form narrow" onSubmit={onSubmit}>
      <h1>로그인</h1>
      {params.get("registered") && <p className="ok" role="status">가입이 완료되었습니다. 입력한 주소로 인증 메일을 보냈습니다. 로그인한 뒤 메일의 링크를 눌러 인증을 마쳐 주세요.</p>}
      {params.get("deleted") && <p className="ok" role="status">계정을 삭제했습니다. 그동안 이용해 주셔서 감사합니다.</p>}
      {params.get("reset") && <p className="ok" role="status">비밀번호를 바꿨습니다. 모든 기기에서 로그아웃되었으니 새 비밀번호로 로그인해 주세요.</p>}
      <label>이메일<input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
      <label>비밀번호<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
      {needOtp && (
        <label>2단계 인증 코드
          <input value={otp} onChange={(e) => setOtp(e.target.value)} inputMode="numeric" autoComplete="one-time-code" autoFocus
            placeholder="인증 앱의 6자리 숫자 또는 복구 코드" required />
          <span className="hint">인증 앱을 쓸 수 없으면 켤 때 받은 복구 코드(예: abcd-2345)를 입력하세요.</span>
        </label>
      )}
      {err && <p className="error" role="alert">{err}</p>}
      <button className="btn primary" disabled={busy}>{busy ? "확인 중…" : "로그인"}</button>
      <p className="muted"><Link href="/forgot-password">비밀번호를 잊으셨나요?</Link></p>
      <p className="muted">계정이 없나요? <Link href={next === "/" ? "/register" : `/register?next=${encodeURIComponent(next)}`}>가입</Link></p>
    </form>
  );
}

export default function LoginPage() {
  return <Suspense fallback={null}><LoginForm /></Suspense>;
}
