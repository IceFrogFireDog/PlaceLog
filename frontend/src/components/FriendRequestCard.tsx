"use client";
import Link from "next/link";
import { useState } from "react";
import { ApiError, api, errorMessage } from "@/lib/api";
import type { RelationStatus, UserBrief } from "@/lib/types";
import { Avatar } from "./Avatar";

interface Props {
  user: UserBrief; status: RelationStatus; friendshipId: string | null; onChanged: () => void;
  /** 카드가 새로고침으로 사라져도 보이도록 페이지에 안내를 넘긴다 */
  onNotice?: (msg: string) => void;
}

export function FriendRequestCard({ user, status, friendshipId, onChanged, onNotice }: Props) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true); setErr(null);
    try {
      await fn();
      onChanged();
    } catch (e) {
      const msg = errorMessage(e);
      if (e instanceof ApiError && (e.status === 404 || e.status === 409)) {
        // 상대가 이미 취소·수락했거나 반대 요청이 있음 → 화면이 오래된 상태이므로 목록을 다시 불러온다
        if (onNotice) onNotice(`${msg} 목록을 새로 고쳤습니다.`);
        else setErr(msg);
        onChanged();
      } else setErr(msg);
    } finally { setBusy(false); }
  }

  return (
    <div className="friend-card">
      <Link href={`/users/${user.username}`} className="user-chip"><Avatar user={user} size={32} /><span><strong>{user.display_name}</strong> <span className="muted">@{user.username}</span></span></Link>
      <div className="actions">
        {status === "NONE" && <button className="btn primary" disabled={busy} onClick={() => run(() => api("/friends/requests", { method: "POST", json: { target_user_id: user.id } }))}>친구 요청</button>}
        {status === "OUTGOING" && friendshipId && <button className="btn" disabled={busy} onClick={() => run(() => api(`/friends/${friendshipId}`, { method: "DELETE" }))}>요청 취소</button>}
        {status === "INCOMING" && friendshipId && (
          <>
            <button className="btn primary" disabled={busy} onClick={() => run(() => api(`/friends/${friendshipId}/accept`, { method: "POST" }))}>수락</button>
            <button className="btn" disabled={busy} onClick={() => run(() => api(`/friends/${friendshipId}/reject`, { method: "POST" }))}>거절</button>
          </>
        )}
        {status === "FRIENDS" && friendshipId && <button className="btn" disabled={busy} onClick={() => confirm("친구를 해제할까요?") && run(() => api(`/friends/${friendshipId}`, { method: "DELETE" }))}>친구 해제</button>}
      </div>
      {err && <p className="error">{err}</p>}
    </div>
  );
}
