"use client";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { onAuthStale } from "@/lib/api";
import { fetchMe } from "@/lib/auth";
import type { Me } from "@/lib/types";

interface AuthState { user: Me | null; loading: boolean; refresh: () => Promise<void>; setUser: (u: Me | null) => void }
const AuthContext = createContext<AuthState>({ user: null, loading: true, refresh: async () => {}, setUser: () => {} });
const CHANNEL = "photo-globe-auth";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUserState] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const currentId = useRef<string | null>(null);
  const channel = useRef<BroadcastChannel | null>(null);

  const apply = useCallback((me: Me | null) => {
    const prev = currentId.current;
    currentId.current = me?.id ?? null;
    // 다른 탭에서 다른 계정으로 로그인함 → 이 탭의 이전 사용자 데이터(친구 관계, 수정 버튼 등)를 모두 버린다
    if (prev && me && prev !== me.id) {
      window.location.reload();
      return;
    }
    setUserState(me);
    setLoading(false);
  }, []);

  const refresh = useCallback(async () => { apply(await fetchMe()); }, [apply]);

  /** 이 탭에서 로그인·로그아웃했을 때: 상태 반영 + 다른 탭에 알림 */
  const setUser = useCallback((u: Me | null) => {
    currentId.current = u?.id ?? null;
    setUserState(u);
    setLoading(false);
    try { channel.current?.postMessage("changed"); } catch { /* 지원 안 하는 브라우저 */ }
  }, []);

  useEffect(() => {
    void refresh();
    const onVisible = () => { if (document.visibilityState === "visible") void refresh(); };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    try {
      channel.current = new BroadcastChannel(CHANNEL);
      channel.current.onmessage = () => { void refresh(); };
    } catch { channel.current = null; }
    const off = onAuthStale(() => { void refresh(); });
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
      channel.current?.close();
      off();
    };
  }, [refresh]);

  return <AuthContext.Provider value={{ user, loading, refresh, setUser }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
