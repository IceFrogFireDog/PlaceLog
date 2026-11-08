"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ApiError, errorMessage } from "@/lib/api";
import { logout } from "@/lib/auth";
import { useAuth } from "./AuthProvider";
import { Avatar } from "./Avatar";

export function Navbar() {
  const { user, loading, setUser } = useAuth();
  const router = useRouter();

  async function onLogout() {
    try {
      await logout();
    } catch (e) {
      // 401이면 이미 세션이 없음 → 로그아웃된 것으로 처리. 그 외(CSRF·네트워크)는 쿠키가 남아 있으므로 상태 유지.
      if (!(e instanceof ApiError && e.status === 401)) {
        alert(`로그아웃하지 못했습니다: ${errorMessage(e)} 새로고침 후 다시 시도해 주세요.`);
        return;
      }
    }
    setUser(null);
    router.push("/");
  }

  return (
    <header className="navbar">
      <Link href="/" className="brand">◐ 지구본 사진</Link>
      <Suspense fallback={<div className="nav-search" />}><NavSearch /></Suspense>
      <nav>
        {loading ? null : user ? (
          <>
            <Link href="/upload" className="btn primary">등록</Link>
            <Link href="/friends">친구</Link>
            {user.is_admin && <Link href="/admin">관리</Link>}
            <Link href={`/users/${user.username}`} className="me" title={user.display_name}><Avatar user={user} size={26} /><span>{user.display_name}</span></Link>
            <button className="link" onClick={onLogout}>로그아웃</button>
          </>
        ) : (
          <>
            <Link href="/login">로그인</Link>
            <Link href="/register" className="btn primary">가입</Link>
          </>
        )}
      </nav>
    </header>
  );
}

/** 검색창 값을 주소의 ?q=와 맞춘다 (뒤로가기·직접 접속 시에도 일치) */
function NavSearch() {
  const router = useRouter();
  const params = useSearchParams();
  const urlQ = params.get("q") ?? "";
  const [q, setQ] = useState(urlQ);
  const [prevUrlQ, setPrevUrlQ] = useState(urlQ);
  if (urlQ !== prevUrlQ) { setPrevUrlQ(urlQ); setQ(urlQ); }
  return (
    <form className="nav-search" onSubmit={(e) => { e.preventDefault(); if (q.trim()) router.push(`/?q=${encodeURIComponent(q.trim())}`); }}>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="장소 검색" aria-label="장소 검색" />
    </form>
  );
}
