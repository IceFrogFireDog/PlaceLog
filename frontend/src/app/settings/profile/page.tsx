"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { Avatar } from "@/components/Avatar";
import { RequireAuth } from "@/components/RequireAuth";
import { TwoFactorSettings } from "@/components/TwoFactorSettings";
import { ApiError, api, errorMessage } from "@/lib/api";
import { changePassword } from "@/lib/auth";
import type { Me } from "@/lib/types";
import { validatePassword } from "@/lib/validation";

const AVATAR_ACCEPT = "image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif";

function AvatarSection() {
  const { user, refresh } = useAuth();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  if (!user) return null;

  async function onFile(f: File | undefined) {
    if (!f) return;
    if (f.size > 20 * 1024 * 1024) return setMsg({ ok: false, text: "20MB 이하 파일만 올릴 수 있습니다." });
    const fd = new FormData();
    fd.set("file", f);
    setBusy(true); setMsg(null);
    try {
      await api("/users/me/avatar", { method: "PUT", form: fd });
      await refresh();
      setMsg({ ok: true, text: "프로필 사진을 바꿨습니다." });
    } catch (e) { setMsg({ ok: false, text: errorMessage(e) }); } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  async function onRemove() {
    if (!confirm("프로필 사진을 지울까요?")) return;
    setBusy(true); setMsg(null);
    try { await api("/users/me/avatar", { method: "DELETE" }); await refresh(); setMsg({ ok: true, text: "프로필 사진을 지웠습니다." }); }
    catch (e) { setMsg({ ok: false, text: errorMessage(e) }); } finally { setBusy(false); }
  }

  return (
    <section className="card stack">
      <h2>프로필 사진</h2>
      <div className="avatar-edit">
        <Avatar user={user} size={96} />
        <div className="stack">
          <label className="btn">{busy ? "처리 중…" : "사진 고르기"}
            <input ref={input} type="file" accept={AVATAR_ACCEPT} className="visually-hidden" disabled={busy} onChange={(e) => onFile(e.target.files?.[0])} />
          </label>
          {user.avatar_url && <button type="button" className="btn danger" onClick={onRemove} disabled={busy}>사진 지우기</button>}
        </div>
      </div>
      <p className="hint">가운데를 정사각형으로 잘라 저장하며, 사진 속 위치정보는 지웁니다. 프로필 사진은 누구나 볼 수 있습니다.</p>
      {msg && <p className={msg.ok ? "ok" : "error"} role="status">{msg.text}</p>}
    </section>
  );
}

/** 처음 값만 채운다: 다른 탭 때문에 사용자 정보가 다시 와도 입력 중인 값을 덮지 않게 (계정이 바뀌면 key로 새로 만든다) */
function ProfileForm({ user }: { user: Me }) {
  const { refresh } = useAuth();
  const router = useRouter();
  const [displayName, setDisplayName] = useState(user.display_name);
  const [bio, setBio] = useState(user.bio);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      await api("/users/me", { method: "PATCH", json: { display_name: displayName, bio } });
      await refresh();
      router.push(`/users/${user.username}`);
    } catch (e) { setErr(errorMessage(e)); setBusy(false); }
  }

  return (
    <form className="card form" onSubmit={onSubmit}>
      <h2>프로필</h2>
      <label>표시명<input value={displayName} maxLength={50} onChange={(e) => setDisplayName(e.target.value)} required /></label>
      <label>소개 <span className="muted">{bio.length}/500</span><textarea value={bio} maxLength={500} rows={4} onChange={(e) => setBio(e.target.value)} /></label>
      {err && <p className="error">{err}</p>}
      <button className="btn primary" disabled={busy}>{busy ? "저장 중…" : "저장"}</button>
    </form>
  );
}

function PasswordForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const local = validatePassword(next, confirm);
    const mapped: Record<string, string> = {};
    if (local.password) mapped.new_password = local.password;
    if (local.confirm) mapped.confirm = local.confirm;
    if (!current) mapped.current_password = "현재 비밀번호를 입력해 주세요.";
    setErrs(mapped); setMsg(null);
    if (Object.keys(mapped).length) return;
    setBusy(true);
    try {
      setMsg({ ok: true, text: (await changePassword(current, next)).message });
      setCurrent(""); setNext(""); setConfirm("");
    } catch (e) {
      setMsg({ ok: false, text: errorMessage(e) });
      if (e instanceof ApiError) setErrs(e.fieldErrors);
    } finally { setBusy(false); }
  }

  return (
    <form className="card form" onSubmit={onSubmit}>
      <h2>비밀번호 변경</h2>
      <label>현재 비밀번호<input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} aria-invalid={!!errs.current_password} />
        {errs.current_password && <span className="error">{errs.current_password}</span>}</label>
      <label>새 비밀번호 (12자 이상)<input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} aria-invalid={!!errs.new_password} />
        {errs.new_password && <span className="error">{errs.new_password}</span>}</label>
      <label>새 비밀번호 확인<input type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} aria-invalid={!!errs.confirm} />
        {errs.confirm && <span className="error">{errs.confirm}</span>}</label>
      {msg && <p className={msg.ok ? "ok" : "error"} role="status">{msg.text}</p>}
      <button className="btn primary" disabled={busy}>{busy ? "바꾸는 중…" : "비밀번호 바꾸기"}</button>
      <p className="hint">바꾸면 지금 쓰는 기기를 뺀 다른 기기에서는 로그아웃됩니다. 비밀번호가 기억나지 않으면 <Link href="/forgot-password">비밀번호 찾기</Link>를 이용하세요.</p>
    </form>
  );
}

function DeleteAccount() {
  const { setUser } = useAuth();
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [ack, setAck] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!ack) return setErr("안내를 읽고 확인란에 체크해 주세요.");
    if (!password) return setErr("비밀번호를 입력해 주세요.");
    if (!confirm("정말 계정을 삭제할까요? 사진과 친구 관계가 모두 지워지며 되돌릴 수 없습니다.")) return;
    setBusy(true);
    try {
      await api("/users/me", { method: "DELETE", json: { password } });
      setUser(null);
      router.replace("/login?deleted=1");
    } catch (e) { setErr(errorMessage(e)); setBusy(false); }
  }

  return (
    <form className="card form danger-zone" onSubmit={onSubmit}>
      <h2>계정 삭제</h2>
      <ul className="hint">
        <li>올린 사진(원본 포함)·프로필 사진·친구 관계·로그인 기록이 바로 지워지며 되돌릴 수 없습니다.</li>
        <li>내가 만든 장소 중 다른 사람의 사진이 있는 곳은 공유 장소로 남고, 만든 사람 정보만 지워집니다.</li>
        <li>같은 이메일로 다시 가입할 수 있습니다.</li>
      </ul>
      <label>비밀번호 확인<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
      <label className="check"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />위 내용을 이해했으며 계정을 삭제합니다.</label>
      {err && <p className="error" role="alert">{err}</p>}
      <button className="btn danger" disabled={busy}>{busy ? "삭제 중…" : "계정 삭제"}</button>
    </form>
  );
}

function Settings() {
  const { user } = useAuth();
  if (!user) return null; // RequireAuth가 로그인 상태에서만 보여 준다
  // 백엔드가 아직 제공하지 않는 기능은 숨긴다: 프로필 사진·비밀번호 변경은 3차, 2단계 인증·계정 삭제는 4차부터
  const hasMailFeatures = user.email_verified !== undefined;
  const hasAccountSecurity = user.two_factor_enabled !== undefined;
  return (
    <div className="narrow stack">
      <h1>설정</h1>
      {hasMailFeatures && <AvatarSection />}
      <ProfileForm key={user.id} user={user} />
      {hasMailFeatures && <PasswordForm key={`pw-${user.id}`} />}
      {hasAccountSecurity && <TwoFactorSettings key={`2fa-${user.id}`} />}
      <section className="card">
        <h2>계정</h2>
        <p>이메일: {user.email} {user.email_verified === true && <span className="badge vis-public">인증됨</span>}{user.email_verified === false && <span className="badge">인증 전</span>}</p>
      </section>
      {hasAccountSecurity && <DeleteAccount key={`del-${user.id}`} />}
    </div>
  );
}

export default function SettingsPage() {
  return <RequireAuth><Settings /></RequireAuth>;
}
