"use client";
import { ErrorState } from "@/components/ErrorState";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCursorStack } from "@/hooks/useCursorStack";
import { useRefreshWhile } from "@/hooks/useRefreshWhile";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { FriendRequestCard } from "@/components/FriendRequestCard";
import { Pagination } from "@/components/Pagination";
import { PhotoGrid } from "@/components/PhotoGrid";
import { ProfileHeader } from "@/components/ProfileHeader";
import { api, errorMessage, isNotFound } from "@/lib/api";
import type { Page, PhotoListItem, PlaceDetail, Profile } from "@/lib/types";

function UserPageInner() {
  const { username } = useParams<{ username: string }>();
  const { user } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [places, setPlaces] = useState<PlaceDetail[]>([]);
  const [placesErr, setPlacesErr] = useState<string | null>(null);
  const [page, setPage] = useState<Page<PhotoListItem> | null>(null);
  const pager = useCursorStack();
  const [loadedKey, setLoadedKey] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const cursor = pager.cursor;
  const viewer = user?.id ?? "";
  const key = `${username}|${cursor ?? ""}|${viewer}`;
  const loading = loadedKey !== key;

  const loadProfile = useCallback(() => {
    api<Profile>(`/users/${username}`).then(setProfile).catch((e) => setErr(errorMessage(e)));
    // 없는 사용자는 위 프로필 요청이 알려 준다. 목록의 404는 사진 기능이 없는 백엔드(1차) → 빈 목록
    api<Page<PlaceDetail>>(`/users/${username}/places`, { query: { limit: 100 } }).then((r) => { setPlaces(r.items); setPlacesErr(null); })
      .catch((e) => (isNotFound(e) ? setPlaces([]) : setPlacesErr(errorMessage(e))));
  }, [username]);
  useEffect(() => { loadProfile(); }, [loadProfile, viewer]);
  // 변환 중인 내 사진이 있으면 끝날 때까지 몇 초마다 다시 불러온다
  const tick = useRefreshWhile(!!page?.items.some((p) => p.status === "PROCESSING"));
  useEffect(() => {
    api<Page<PhotoListItem>>(`/users/${username}/photos`, { query: { cursor } }).then(setPage)
      .catch((e) => (isNotFound(e) ? setPage({ items: [], next_cursor: null }) : setErr(errorMessage(e)))).finally(() => setLoadedKey(key));
  }, [username, cursor, viewer, key, tick]);

  if (err) return <ErrorState message={err} />;
  if (!profile) return <p className="muted center">불러오는 중…</p>;
  const self = profile.relation.status === "SELF";
  return (
    <div className="stack">
      <ProfileHeader profile={profile} />
      {self && <Link className="btn" href="/settings/profile">프로필 수정</Link>}
      {user && !self && <FriendRequestCard user={profile} status={profile.relation.status} friendshipId={profile.relation.friendship_id} onChanged={loadProfile} />}
      {placesErr && <p className="error">기록한 장소를 불러오지 못했습니다: {placesErr}</p>}
      {places.length > 0 && (
        <section>
          <h2>기록한 장소</h2>
          <ul className="chips">{places.map((p) => <li key={p.id}><Link href={`/places/${p.id}`}>{p.name} <span className="muted">{p.photo_count}</span></Link></li>)}</ul>
        </section>
      )}
      <section>
        <h2>사진</h2>
        {!page && loading && <p className="muted">사진 불러오는 중…</p>}
        {page && <PhotoGrid photos={page.items} showOwner={false} />}
        <Pagination hasPrev={pager.hasPrev} hasNext={!!page?.next_cursor} loading={loading}
          onPrev={pager.prev} onNext={() => page?.next_cursor && pager.next(page.next_cursor)} />
      </section>
    </div>
  );
}

export default function UserPage() {
  return <Suspense fallback={<p className="muted center">불러오는 중…</p>}><UserPageInner /></Suspense>;
}
