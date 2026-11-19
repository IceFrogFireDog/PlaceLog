"use client";
import { ErrorState } from "@/components/ErrorState";
import { useParams } from "next/navigation";
import { useCursorStack } from "@/hooks/useCursorStack";
import { useRefreshWhile } from "@/hooks/useRefreshWhile";
import { Suspense, useEffect, useState } from "react";
import { Pagination } from "@/components/Pagination";
import { PhotoGrid } from "@/components/PhotoGrid";
import { api, errorMessage } from "@/lib/api";
import type { Page, PhotoListItem, PlaceDetail } from "@/lib/types";

function PlacePageInner() {
  const { id } = useParams<{ id: string }>();
  const [place, setPlace] = useState<PlaceDetail | null>(null);
  const [page, setPage] = useState<Page<PhotoListItem> | null>(null);
  const pager = useCursorStack();
  const [loadedKey, setLoadedKey] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const cursor = pager.cursor;
  const key = `${id}|${cursor ?? ""}`;
  const loading = loadedKey !== key;

  // 변환 중인 사진이 있으면 끝날 때까지 몇 초마다 다시 불러온다
  const tick = useRefreshWhile(!!page?.items.some((p) => p.status === "PROCESSING"));
  useEffect(() => { api<PlaceDetail>(`/places/${id}`).then(setPlace).catch((e) => setErr(errorMessage(e))); }, [id, tick]);
  useEffect(() => {
    api<Page<PhotoListItem>>(`/places/${id}/photos`, { query: { cursor } })
      .then(setPage).catch((e) => setErr(errorMessage(e))).finally(() => setLoadedKey(key));
  }, [id, cursor, key, tick]);

  if (err) return <ErrorState message={err} />;
  return (
    <div className="stack">
      {place ? (
        <header>
          <h1>{place.name}</h1>
          <p className="muted">{[[place.address, place.city, place.country_code].filter(Boolean).join(", "), `${place.latitude.toFixed(4)}, ${place.longitude.toFixed(4)}`, `볼 수 있는 사진 ${place.photo_count}장`].filter(Boolean).join(" · ")}</p>
        </header>
      ) : <p className="muted">불러오는 중…</p>}
      {!page && loading && <p className="muted">사진 불러오는 중…</p>}
      {page && <PhotoGrid photos={page.items} />}
      <Pagination hasPrev={pager.hasPrev} hasNext={!!page?.next_cursor} loading={loading}
        onPrev={pager.prev} onNext={() => page?.next_cursor && pager.next(page.next_cursor)} />
    </div>
  );
}

export default function PlacePage() {
  return <Suspense fallback={<p className="muted center">불러오는 중…</p>}><PlacePageInner /></Suspense>;
}
