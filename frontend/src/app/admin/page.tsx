"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { RequireAuth } from "@/components/RequireAuth";
import { api, errorMessage } from "@/lib/api";

interface Stats {
  users: number; verified_users: number; suspended_users: number; two_factor_users: number; places: number; friendships: number;
  photos: { PROCESSING: number; READY: number; FAILED: number };
}
interface AdminUser {
  id: string; email: string; username: string; display_name: string; created_at: string;
  email_verified: boolean; two_factor_enabled: boolean; is_admin: boolean; suspended: boolean; photo_count: number;
}
interface DupPlace { id: string; name: string; latitude: number; longitude: number; photo_count: number }
interface DupPair { a: DupPlace; b: DupPlace; distance_m: number }

function StatsCard() {
  const [s, setS] = useState<Stats | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api<Stats>("/admin/stats").then(setS).catch((e) => setErr(errorMessage(e))); }, []);
  if (err) return <p className="error">{err}</p>;
  if (!s) return <p className="muted">불러오는 중…</p>;
  const items: [string, number][] = [
    ["사용자", s.users], ["이메일 인증", s.verified_users], ["2단계 인증", s.two_factor_users], ["정지", s.suspended_users],
    ["장소", s.places], ["친구 관계", s.friendships], ["사진", s.photos.READY], ["변환 중", s.photos.PROCESSING], ["변환 실패", s.photos.FAILED],
  ];
  return <ul className="stat-grid">{items.map(([k, v]) => <li key={k}><strong>{v.toLocaleString("ko-KR")}</strong><span>{k}</span></li>)}</ul>;
}

function Users() {
  const { user: me } = useAuth();
  const [q, setQ] = useState("");
  const [applied, setApplied] = useState("");
  const [rows, setRows] = useState<AdminUser[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // 검색어가 바뀌면 첫 페이지부터
  useEffect(() => {
    let alive = true;
    api<{ items: AdminUser[]; next_cursor: string | null }>("/admin/users", { query: { q: applied, limit: 50 } })
      .then((page) => { if (alive) { setRows(page.items); setNext(page.next_cursor); setErr(null); } })
      .catch((e) => { if (alive) setErr(errorMessage(e)); });
    return () => { alive = false; };
  }, [applied]);

  async function more() {
    if (!next) return;
    try {
      const page = await api<{ items: AdminUser[]; next_cursor: string | null }>("/admin/users", { query: { q: applied, cursor: next, limit: 50 } });
      setRows((prev) => [...prev, ...page.items]);
      setNext(page.next_cursor);
    } catch (e) { setErr(errorMessage(e)); }
  }

  async function toggle(u: AdminUser) {
    const verb = u.suspended ? "정지를 풀까요" : "이용을 정지할까요? 바로 로그아웃되고 다시 로그인할 수 없습니다";
    if (!confirm(`${u.display_name}(@${u.username})의 ${verb}?`)) return;
    setBusy(u.id);
    try {
      const r = await api<AdminUser>(`/admin/users/${u.id}/suspend`, { method: "POST", json: { suspended: !u.suspended } });
      setRows((prev) => prev.map((x) => (x.id === u.id ? { ...x, suspended: r.suspended } : x)));
    } catch (e) { setErr(errorMessage(e)); } finally { setBusy(null); }
  }

  return (
    <section className="card stack">
      <h2>사용자</h2>
      <form className="row" onSubmit={(e) => { e.preventDefault(); setApplied(q.trim()); }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="이메일·닉네임·표시명" aria-label="사용자 검색" />
        <button className="btn">검색</button>
      </form>
      {err && <p className="error">{err}</p>}
      <div className="table-wrap">
        <table className="admin-table">
          <thead><tr><th>사용자</th><th>이메일</th><th>가입</th><th>사진</th><th>상태</th><th /></tr></thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id} className={u.suspended ? "suspended" : ""}>
                <td><Link href={`/users/${u.username}`}>{u.display_name}</Link> <span className="muted">@{u.username}</span>{u.is_admin && <span className="badge">관리자</span>}</td>
                <td>{u.email}</td>
                <td>{new Date(u.created_at).toLocaleDateString("ko-KR")}</td>
                <td>{u.photo_count}</td>
                <td>{[u.suspended ? "정지" : "정상", u.email_verified ? "인증" : "미인증", u.two_factor_enabled ? "2단계" : null].filter(Boolean).join(" · ")}</td>
                <td>{u.id !== me?.id && !u.is_admin && (
                  <button className={`btn ${u.suspended ? "" : "danger"}`} disabled={busy === u.id} onClick={() => toggle(u)}>{u.suspended ? "정지 해제" : "정지"}</button>
                )}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length === 0 && !err && <p className="muted">사용자가 없습니다.</p>}
      {next && <button className="btn" onClick={() => void more()}>더 보기</button>}
    </section>
  );
}

function Duplicates() {
  const [pairs, setPairs] = useState<DupPair[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const load = useCallback(() => { api<DupPair[]>("/admin/places/duplicates").then(setPairs).catch((e) => setErr(errorMessage(e))); }, []);
  useEffect(() => { load(); }, [load]);

  async function merge(source: DupPlace, target: DupPlace) {
    if (!confirm(`'${source.name}'의 사진 ${source.photo_count}장을 '${target.name}'(으)로 옮기고 '${source.name}'을(를) 지울까요?`)) return;
    try {
      const r = await api<{ moved: number }>("/admin/places/merge", { method: "POST", json: { source_id: source.id, target_id: target.id } });
      setMsg(`사진 ${r.moved}장을 옮기고 장소를 합쳤습니다.`); load();
    } catch (e) { setErr(errorMessage(e)); }
  }

  return (
    <section className="card stack">
      <h2>중복 장소 <span className="muted">같은 이름·200m 이내</span></h2>
      {err && <p className="error">{err}</p>}
      {msg && <p className="ok" role="status">{msg}</p>}
      {!pairs ? <p className="muted">불러오는 중…</p> : pairs.length === 0 ? <p className="muted">합칠 후보가 없습니다.</p> : (
        <ul className="list">
          {pairs.map(({ a, b, distance_m }) => (
            <li key={`${a.id}-${b.id}`} className="dup-pair">
              <span><Link href={`/places/${a.id}`}>{a.name}</Link> <span className="muted">사진 {a.photo_count}</span> ↔ <Link href={`/places/${b.id}`}>{b.name}</Link> <span className="muted">사진 {b.photo_count} · {distance_m}m</span></span>
              <span className="actions">
                <button className="btn" onClick={() => merge(b, a)}>{a.name}(으)로 합치기</button>
                <button className="btn" onClick={() => merge(a, b)}>{b.name}(으)로 합치기</button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Admin() {
  const { user } = useAuth();
  if (!user?.is_admin) return <div className="card center"><p>관리자만 볼 수 있는 화면입니다.</p></div>;
  return (
    <div className="stack">
      <h1>관리</h1>
      <StatsCard />
      <Users />
      <Duplicates />
      <p className="hint">관리자 지정·해제는 서버에서 <code>python -m app.tasks make-admin 이메일 [--revoke]</code>로 합니다. 사진 신고 처리는 사진 화면의 &lsquo;관리자 삭제&rsquo; 버튼을 쓰세요.</p>
    </div>
  );
}

export default function AdminPage() {
  return <RequireAuth><Admin /></RequireAuth>;
}
