"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useAuth } from "./AuthProvider";

/**
 * 화면용 안내일 뿐이며 실제 권한은 서버가 검사한다.
 * keepOnLogout: 업로드·수정처럼 작성 중인 화면은 세션이 끊겨도 입력 내용을 지우지 않고 안내만 띄운다.
 */
export function RequireAuth({ children, keepOnLogout = false }: { children: React.ReactNode; keepOnLogout?: boolean }) {
  const { user, loading } = useAuth();
  const path = usePathname();
  const [wasAuthed, setWasAuthed] = useState(false);
  if (user && !wasAuthed) setWasAuthed(true);
  const loginHref = `/login?next=${encodeURIComponent(path)}`;

  const sessionLost = !user && keepOnLogout && wasAuthed;
  // 배너 유무와 상관없이 children의 트리 위치를 같게 유지해야 React가 폼을 다시 만들지 않는다 (입력 내용 보존)
  if (user || sessionLost)
    return (
      <>
        {sessionLost ? (
          <div className="session-banner" role="alert">
            로그인이 끊겼습니다. 작성 중인 내용은 그대로 있습니다.{" "}
            <a href={loginHref} target="_blank" rel="noopener">새 탭에서 로그인</a>한 뒤 이 탭으로 돌아와 다시 시도해 주세요.
          </div>
        ) : null}
        {children}
      </>
    );
  if (loading) return <p className="muted center">불러오는 중…</p>;
  return (
    <div className="card center">
      <p>로그인이 필요한 화면입니다.</p>
      <Link className="btn primary" href={loginHref}>로그인</Link>
    </div>
  );
}
