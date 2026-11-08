"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { Globe } from "@/components/Globe/Globe";
import { MapFilters } from "@/components/Globe/MapFilters";
import { PlacePanel } from "@/components/Globe/PlacePanel";
import { useMapPlaces } from "@/hooks/useMapPlaces";
import { api, errorMessage, isNotFound } from "@/lib/api";
import type { GlobeView, MapItem, MapMode, Page, Place } from "@/lib/types";

function Home() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [mode, setMode] = useState<MapMode>("WORLD");
  const [view, setView] = useState<GlobeView>({ bbox: null, zoom: 2 });
  const [selected, setSelected] = useState<string | null>(null);
  const [focus, setFocus] = useState<{ lat: number; lng: number; seq: number; zoomIn?: boolean } | null>(null);
  const [search, setSearch] = useState<{ q: string; items: Place[]; err: string | null } | null>(null);
  // 로그아웃 상태에서는 전체 지도만 볼 수 있다
  const activeMode: MapMode = user ? mode : "WORLD";
  const { items, loading, error, reload } = useMapPlaces(activeMode, view, !authLoading);

  // 계정이 바뀌면(로그인·로그아웃·다른 계정) 이전 사용자 권한으로 고른 장소·지도 모드를 버린다
  const uid = user?.id ?? null;
  const [seenUid, setSeenUid] = useState<string | null | undefined>(undefined);
  if (!authLoading && seenUid !== uid) {
    if (seenUid !== undefined) { setSelected(null); setMode("WORLD"); }
    setSeenUid(uid);
  }
  // 핀도 새 권한으로 다시 불러온다
  const prevUid = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    if (authLoading) return;
    if (prevUid.current !== undefined && prevUid.current !== uid) reload();
    prevUid.current = uid;
  }, [uid, authLoading, reload]);

  // 상단 검색(?q=) → 장소 검색 결과 (검색어별로 저장해 늦게 온 이전 응답이 섞이지 않게)
  const q = params.get("q");
  useEffect(() => {
    if (!q) return;
    const ctl = new AbortController();
    api<Page<Place>>("/places", { query: { q, limit: 10 }, signal: ctl.signal })
      .then((r) => setSearch({ q, items: r.items, err: null }))
      .catch((e) => { if ((e as Error).name !== "AbortError") setSearch({ q, items: [], err: isNotFound(e) ? null : errorMessage(e) }); });
    return () => ctl.abort();
  }, [q]);
  const current = q && search?.q === q ? search : null;
  const results = current?.items ?? null;
  const searchErr = current?.err ?? null;

  const onSelect = useCallback((it: MapItem) => {
    if (it.kind === "cluster") setFocus({ lat: it.latitude, lng: it.longitude, seq: Date.now(), zoomIn: true }); // 클러스터 → 확대
    else setSelected(it.place_id);
  }, []);

  return (
    <div className="home">
      <Globe items={items} selectedId={selected} focus={focus} onSelect={onSelect} onViewChange={setView} />
      <div className="map-status">
        {loading && <span className="muted">핀 불러오는 중…</span>}
        {error && <span className="error">{error} <button className="link" onClick={reload}>다시 시도</button></span>}
        {!loading && !error && items.length === 0 && <span className="muted">이 범위에 볼 수 있는 사진이 없습니다.</span>}
      </div>
      {results && (
        <div className="search-results card">
          <div className="row"><strong>“{q}” 검색 결과</strong><button className="link" onClick={() => router.push("/")}>닫기</button></div>
          {searchErr ? <p className="error">{searchErr}</p> : results.length === 0 ? <p className="muted">결과가 없습니다.</p> : (
            <ul className="list">
              {results.map((p) => (
                <li key={p.id}><button className="link" onClick={() => { setSelected(p.id); setFocus({ lat: p.latitude, lng: p.longitude, seq: Date.now() }); }}>{p.name}</button></li>
              ))}
            </ul>
          )}
        </div>
      )}
      {selected && <PlacePanel placeId={selected} onClose={() => setSelected(null)} />}
      <MapFilters mode={activeMode} onChange={setMode} loggedIn={!!user} />
    </div>
  );
}

export default function Page() {
  return <Suspense fallback={null}><Home /></Suspense>;
}
