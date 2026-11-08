"use client";
import { useCallback, useEffect, useState } from "react";
import { FriendRequestCard } from "@/components/FriendRequestCard";
import { RequireAuth } from "@/components/RequireAuth";
import { api, errorMessage } from "@/lib/api";
import type { Friendship, Page, SearchUser } from "@/lib/types";

function Friends() {
  const [q, setQ] = useState("");
  const [found, setFound] = useState<SearchUser[] | null>(null);
  const [incoming, setIncoming] = useState<Friendship[]>([]);
  const [outgoing, setOutgoing] = useState<Friendship[]>([]);
  const [friends, setFriends] = useState<Friendship[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [more, setMore] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const [i, o, f] = await Promise.all([
        api<Page<Friendship>>("/friends/requests", { query: { direction: "incoming", limit: 100 } }),
        api<Page<Friendship>>("/friends/requests", { query: { direction: "outgoing", limit: 100 } }),
        api<Page<Friendship>>("/friends", { query: { limit: 100 } }),
      ]);
      setIncoming(i.items); setOutgoing(o.items); setFriends(f.items);
      setMore(!!(i.next_cursor || o.next_cursor || f.next_cursor));
      if (q.trim()) setFound((await api<Page<SearchUser>>("/users/search", { query: { q } })).items);
    } catch (e) { setErr(errorMessage(e)); } finally { setLoading(false); }
  }, [q]);

  useEffect(() => { void load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    try { setFound((await api<Page<SearchUser>>("/users/search", { query: { q } })).items); } catch (e) { setErr(errorMessage(e)); }
  }

  const section = (title: string, list: Friendship[], status: "INCOMING" | "OUTGOING" | "FRIENDS", empty: string) => (
    <section className="card">
      <h2>{title} <span className="muted">{list.length}</span></h2>
      {list.length === 0 ? <p className="muted">{empty}</p> : list.map((f) => <FriendRequestCard key={f.id} user={f.user} status={status} friendshipId={f.id} onChanged={load} onNotice={setNotice} />)}
    </section>
  );

  return (
    <div className="narrow stack">
      <h1>친구</h1>
      <form className="card row" onSubmit={search}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="닉네임 또는 표시명" aria-label="사용자 검색" />
        <button className="btn primary">검색</button>
      </form>
      {found && (
        <section className="card">
          <h2>검색 결과</h2>
          {found.length === 0 ? <p className="muted">찾는 사용자가 없습니다.</p> : found.map((u) => <FriendRequestCard key={u.id} user={u} status={u.relation.status} friendshipId={u.relation.friendship_id} onChanged={load} onNotice={setNotice} />)}
        </section>
      )}
      {notice && <p className="notice" role="status">{notice} <button className="link" onClick={() => setNotice(null)}>닫기</button></p>}
      {err && <p className="error">{err}</p>}
      {loading ? <p className="muted">불러오는 중…</p> : (
        <>
          {section("받은 요청", incoming, "INCOMING", "받은 요청이 없습니다.")}
          {section("보낸 요청", outgoing, "OUTGOING", "보낸 요청이 없습니다.")}
          {section("친구", friends, "FRIENDS", "아직 친구가 없습니다.")}
          {more && <p className="muted">각 목록은 최근 100명까지 표시합니다.</p>}
        </>
      )}
    </div>
  );
}

export default function FriendsPage() {
  return <RequireAuth><Friends /></RequireAuth>;
}
