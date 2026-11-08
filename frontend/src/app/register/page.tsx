"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ApiError } from "@/lib/api";
import { register, safeNext } from "@/lib/auth";
import { validateRegister } from "@/lib/validation";

function RegisterForm() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [v, setV] = useState({ email: "", username: "", display_name: "", password: "", confirm: "" });
  const [agree, setAgree] = useState(false);
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof v) => (e: React.ChangeEvent<HTMLInputElement>) => setV({ ...v, [k]: e.target.value });

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const local = validateRegister({ ...v, agree_privacy: agree });
    setErrs(local); setMsg(null);
    if (Object.keys(local).length) return;
    setBusy(true);
    try {
      await register({ email: v.email, username: v.username, display_name: v.display_name, password: v.password, agree_privacy: agree });
      router.push(`/login?registered=1${next === "/" ? "" : `&next=${encodeURIComponent(next)}`}`);
    } catch (err) {
      if (err instanceof ApiError) { setErrs(err.fieldErrors); setMsg(err.message); } else setMsg("가입에 실패했습니다.");
    } finally { setBusy(false); }
  }

  const field = (k: keyof typeof v, label: string, type = "text", extra: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <label>{label}<input type={type} value={v[k]} onChange={set(k)} aria-invalid={!!errs[k]} {...extra} />{errs[k] && <span className="error">{errs[k]}</span>}</label>
  );

  return (
    <form className="card form narrow" onSubmit={onSubmit}>
      <h1>가입</h1>
      {field("email", "이메일 (인증 메일을 받을 주소)", "email", { autoComplete: "email" })}
      {field("username", "닉네임 (영문·숫자·밑줄 3~30자)", "text", { autoComplete: "username" })}
      {field("display_name", "표시명 (한글 가능)")}
      {field("password", "비밀번호 (12자 이상)", "password", { autoComplete: "new-password" })}
      {field("confirm", "비밀번호 확인", "password", { autoComplete: "new-password" })}
      <div className="consent">
        <label className="check">
          <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} aria-invalid={!!errs.agree_privacy} />
          <span>(필수) <Link href="/privacy" target="_blank" rel="noopener">개인정보 처리 안내</Link>를 읽었으며 동의합니다.</span>
        </label>
        <p className="hint">사진의 GPS 좌표 등 위치정보를 다룹니다. 수집 항목·이용 목적·보관 기간은 안내 페이지에 있습니다.</p>
        {errs.agree_privacy && <span className="error">{errs.agree_privacy}</span>}
      </div>
      {msg && <p className="error" role="alert">{msg}</p>}
      <button className="btn primary" disabled={busy}>{busy ? "처리 중…" : "가입"}</button>
      <p className="muted">이미 계정이 있나요? <Link href={next === "/" ? "/login" : `/login?next=${encodeURIComponent(next)}`}>로그인</Link></p>
    </form>
  );
}

export default function RegisterPage() {
  return <Suspense fallback={null}><RegisterForm /></Suspense>;
}
