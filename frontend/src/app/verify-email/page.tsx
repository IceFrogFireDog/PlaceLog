"use client";
import Link from "next/link";
import { Suspense, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { useUrlToken } from "@/hooks/useUrlToken";
import { ApiError, errorMessage } from "@/lib/api";
import { resendVerification, verifyEmail } from "@/lib/auth";

function Verify() {
  const token = useUrlToken();
  const { user, refresh } = useAuth();
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [msg, setMsg] = useState<string | null>(null);
  const [resendMsg, setResendMsg] = useState<string | null>(null);

  // 메일 보안 검사기가 링크를 미리 열어도 인증되지 않도록 자동 실행하지 않고 버튼으로 확인한다
  async function onVerify() {
    if (!token) return;
    setState("busy"); setMsg(null);
    try {
      setMsg((await verifyEmail(token)).message);
      setState("done");
      await refresh();
    } catch (e) {
      setState("error");
      setMsg(e instanceof ApiError && e.code === "TOKEN_INVALID"
        ? "링크가 만료되었거나 이미 사용되었습니다. 로그인한 뒤 인증 메일을 다시 받아 주세요."
        : errorMessage(e));
    }
  }

  async function onResend() {
    setResendMsg(null);
    try { setResendMsg((await resendVerification()).message); } catch (e) { setResendMsg(errorMessage(e)); }
  }

  if (!token) return <div className="card narrow"><h1>이메일 인증</h1><p className="error">링크가 올바르지 않습니다. 메일의 링크를 다시 눌러 주세요.</p></div>;
  return (
    <div className="card narrow stack">
      <h1>이메일 인증</h1>
      {state === "done" ? (
        <>
          <p className="ok" role="status">{msg}</p>
          <p><Link className="btn primary" href={user ? "/upload" : "/login"}>{user ? "사진 등록하러 가기" : "로그인"}</Link></p>
        </>
      ) : (
        <>
          <p>아래 버튼을 누르면 이메일 인증이 완료됩니다.</p>
          <p><button className="btn primary" onClick={onVerify} disabled={state === "busy"}>{state === "busy" ? "확인 중…" : "이메일 인증하기"}</button></p>
          {msg && <p className="error" role="alert">{msg}</p>}
          {state === "error" && user?.email_verified === false && (
            <p><button className="btn" onClick={onResend}>인증 메일 다시 보내기</button> {resendMsg && <span className="muted">{resendMsg}</span>}</p>
          )}
          {state === "error" && !user && <p><Link className="btn" href="/login">로그인</Link></p>}
        </>
      )}
    </div>
  );
}

export default function VerifyEmailPage() {
  return <Suspense fallback={null}><Verify /></Suspense>;
}
