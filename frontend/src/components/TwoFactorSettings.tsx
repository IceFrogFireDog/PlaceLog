"use client";
import qrcode from "qrcode-generator";
import { useEffect, useState } from "react";
import { errorMessage } from "@/lib/api";
import { twoFactorDisable, twoFactorEnable, twoFactorNewCodes, twoFactorSetup, twoFactorStatus } from "@/lib/auth";
import { useAuth } from "./AuthProvider";

function qrDataUrl(text: string): string {
  const qr = qrcode(0, "M");
  qr.addData(text);
  qr.make();
  return qr.createDataURL(5, 2);
}

/** 복구 코드는 이때 한 번만 보여 준다 → 복사·저장 버튼 */
function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const text = `지구본 사진 2단계 인증 복구 코드 (각 코드는 한 번만 사용)\n\n${codes.join("\n")}\n`;
  const [copied, setCopied] = useState(false);
  function download() {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "photo-globe-recovery-codes.txt";
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div className="notice stack" role="status">
      <p><strong>복구 코드를 안전한 곳에 보관하세요.</strong> 인증 앱을 쓸 수 없을 때 로그인에 쓸 수 있고, 각 코드는 한 번만 쓸 수 있습니다. 이 화면을 닫으면 다시 볼 수 없습니다.</p>
      <ul className="recovery-codes">{codes.map((c) => <li key={c}><code>{c}</code></li>)}</ul>
      <div className="actions">
        <button type="button" className="btn" onClick={() => { void navigator.clipboard?.writeText(text).then(() => setCopied(true)).catch(() => {}); }}>{copied ? "복사했습니다" : "복사"}</button>
        <button type="button" className="btn" onClick={download}>텍스트 파일로 저장</button>
        <button type="button" className="btn primary" onClick={onDone}>보관했습니다</button>
      </div>
    </div>
  );
}

export function TwoFactorSettings() {
  const { user, refresh } = useAuth();
  const [left, setLeft] = useState<number | null>(null);
  const [step, setStep] = useState<"idle" | "password" | "scan" | "codes">("idle");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [codes, setCodes] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const enabled = !!user?.two_factor_enabled;

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    twoFactorStatus().then((s) => { if (alive) setLeft(s.recovery_codes_left); }).catch(() => {});
    return () => { alive = false; };
  }, [enabled, codes]);

  async function run(fn: () => Promise<void>) {
    setBusy(true); setErr(null); setMsg(null);
    try { await fn(); } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  }

  const startSetup = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => { setSetup(await twoFactorSetup(password)); setPassword(""); setStep("scan"); });
  };
  const confirmSetup = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => { setCodes((await twoFactorEnable(code.trim())).recovery_codes); setCode(""); setSetup(null); setStep("codes"); await refresh(); });
  };
  const disable = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => { setMsg((await twoFactorDisable(password, code.trim())).message); setPassword(""); setCode(""); await refresh(); });
  };
  const newCodes = () => void run(async () => { setCodes((await twoFactorNewCodes(password, code.trim())).recovery_codes); setPassword(""); setCode(""); setStep("codes"); });

  return (
    <section className="card stack two-factor">
      <h2>2단계 인증 {enabled ? <span className="badge vis-public">켜짐</span> : <span className="badge">꺼짐</span>}</h2>
      <p className="hint">로그인할 때 비밀번호와 함께 휴대폰 인증 앱(Google Authenticator, Microsoft Authenticator 등)의 6자리 코드를 입력합니다.</p>

      {step === "codes" && codes.length > 0 && <RecoveryCodes codes={codes} onDone={() => { setCodes([]); setStep("idle"); }} />}

      {!enabled && step === "idle" && <button type="button" className="btn" onClick={() => setStep("password")}>2단계 인증 켜기</button>}
      {!enabled && step === "password" && (
        <form className="form" onSubmit={startSetup}>
          <label>비밀번호 확인<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          <div className="actions"><button className="btn primary" disabled={busy}>다음</button><button type="button" className="link" onClick={() => setStep("idle")}>취소</button></div>
        </form>
      )}
      {!enabled && step === "scan" && setup && (
        <form className="form" onSubmit={confirmSetup}>
          <p>1. 인증 앱에서 아래 QR 코드를 찍으세요.</p>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="qr" src={qrDataUrl(setup.otpauth_uri)} alt="2단계 인증 등록용 QR 코드" width={180} height={180} />
          <p className="hint">QR을 찍을 수 없으면 키를 직접 입력하세요: <code className="secret">{setup.secret.replace(/(.{4})/g, "$1 ").trim()}</code></p>
          <label>2. 앱에 표시된 6자리 코드<input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" required /></label>
          <div className="actions"><button className="btn primary" disabled={busy}>켜기</button><button type="button" className="link" onClick={() => { setSetup(null); setStep("idle"); }}>취소</button></div>
        </form>
      )}

      {enabled && step !== "codes" && (
        <form className="form" onSubmit={disable}>
          {left !== null && <p className="hint">남은 복구 코드: {left}개{left <= 2 ? " — 새로 만들어 두세요." : ""}</p>}
          <label>비밀번호<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          <label>인증 코드 또는 복구 코드<input value={code} onChange={(e) => setCode(e.target.value)} autoComplete="one-time-code" required /></label>
          <div className="actions">
            <button type="button" className="btn" disabled={busy || !password || !code} onClick={newCodes}>복구 코드 새로 만들기</button>
            <button className="btn danger" disabled={busy}>2단계 인증 끄기</button>
          </div>
        </form>
      )}
      {err && <p className="error" role="alert">{err}</p>}
      {msg && <p className="ok" role="status">{msg}</p>}
    </section>
  );
}
