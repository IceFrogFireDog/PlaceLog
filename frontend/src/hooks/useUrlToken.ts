"use client";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * 메일 링크의 ?token=을 읽어 기억한 뒤 주소창·방문 기록에서 지운다.
 * (화면 공유·스크린샷·브라우저 기록으로 토큰이 새지 않게. 이 화면은 Referrer-Policy: no-referrer)
 */
export function useUrlToken(): string | null {
  const params = useSearchParams();
  const [token] = useState(() => params.get("token"));
  useEffect(() => {
    if (token && window.location.search.includes("token=")) window.history.replaceState(null, "", window.location.pathname);
  }, [token]);
  return token;
}
