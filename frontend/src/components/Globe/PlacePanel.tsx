"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import type { Page, PhotoListItem, PlaceDetail } from "@/lib/types";
import { PhotoGrid } from "../PhotoGrid";

export function PlacePanel({ placeId, onClose }: { placeId: string; onClose: () => void }) {
  // 다른 장소를 고르면 이전 장소 내용이 잠깐이라도 보이지 않게 장소 ID와 함께 저장한다
  const [data, setData] = useState<{ id: string; place: PlaceDetail | null; photos: PhotoListItem[]; error: string | null } | null>(null);

  useEffect(() => {
    const ctl = new AbortController();
    Promise.all([
      api<PlaceDetail>(`/places/${placeId}`, { signal: ctl.signal }),
      api<Page<PhotoListItem>>(`/places/${placeId}/photos`, { query: { limit: 12 }, signal: ctl.signal }),
    ]).then(([p, ph]) => setData({ id: placeId, place: p, photos: ph.items, error: null }))
      .catch((e) => { if ((e as Error).name !== "AbortError") setData({ id: placeId, place: null, photos: [], error: errorMessage(e) }); });
    return () => ctl.abort();
  }, [placeId]);
  const cur = data?.id === placeId ? data : null;
  const place = cur?.place ?? null;
  const photos = cur?.photos ?? null;
  const error = cur?.error ?? null;

  return (
    <aside className="place-panel" aria-label="선택한 장소">
      <button className="close" onClick={onClose} aria-label="닫기">×</button>
      {error ? <p className="error">{error}</p> : !place ? <p className="muted">불러오는 중…</p> : (
        <>
          <h2>{place.name}</h2>
          <p className="muted">{[[place.city, place.country_code].filter(Boolean).join(", "), `볼 수 있는 사진 ${place.photo_count}장`].filter(Boolean).join(" · ")}</p>
          <PhotoGrid photos={photos ?? []} />
          {place.photo_count > (photos?.length ?? 0) && <Link className="btn" href={`/places/${place.id}`}>모두 보기</Link>}
        </>
      )}
    </aside>
  );
}
