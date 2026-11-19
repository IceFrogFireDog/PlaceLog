"use client";
import { useEffect, useState } from "react";

/**
 * active인 동안 intervalMs마다 값이 1씩 늘어난다 (최대 maxTimes번). 데이터를 다시 불러오는 effect의 의존성에 넣어 쓴다.
 * 예: 변환 중(PROCESSING)인 사진이 있으면 목록을 주기적으로 새로 고침.
 */
export function useRefreshWhile(active: boolean, intervalMs = 3000, maxTimes = 40): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!active) return;
    let n = 0;
    const id = setInterval(() => {
      n += 1;
      if (n > maxTimes) { clearInterval(id); return; }
      setTick((t) => t + 1);
    }, intervalMs);
    return () => clearInterval(id);
  }, [active, intervalMs, maxTimes]);
  return tick;
}
