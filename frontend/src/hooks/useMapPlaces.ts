"use client";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, isNotFound } from "@/lib/api";
import type { GlobeView, MapItem, MapMode, MapResponse } from "@/lib/types";

/** 지구본 범위·필터별 핀 조회. 회전 중 호출 간격을 늦추고 이전 요청은 취소한다. */
export function useMapPlaces(mode: MapMode, view: GlobeView, enabled = true) {
  const [items, setItems] = useState<MapItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const bboxKey = view.bbox ? view.bbox.map((v) => v.toFixed(1)).join(",") : "";

  useEffect(() => {
    if (!enabled) return;
    const ctl = new AbortController();
    const t = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api<MapResponse>("/map/places", { query: { mode, zoom: view.zoom, bbox: bboxKey || undefined }, signal: ctl.signal });
        setItems(res.items);
      } catch (e) {
        if (isNotFound(e)) setItems([]); // 지구본 API가 없는 백엔드
        else if ((e as Error).name !== "AbortError") setError(errorMessage(e));
      } finally {
        if (!ctl.signal.aborted) setLoading(false);
      }
    }, 300);
    return () => { clearTimeout(t); ctl.abort(); };
  }, [mode, view.zoom, bboxKey, enabled, reloadKey]);

  const reload = useCallback(() => setReloadKey((k) => k + 1), []);
  return { items, loading, error, reload };
}
