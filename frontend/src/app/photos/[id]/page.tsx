"use client";
import { ErrorState } from "@/components/ErrorState";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { photoStatus, type PhotoDetail } from "@/lib/types";
import { formatDate } from "@/lib/validation";
import { Avatar } from "@/components/Avatar";
import { useAuth } from "@/components/AuthProvider";
import { useRefreshWhile } from "@/hooks/useRefreshWhile";

const VIS = { PUBLIC: "전체 공개", FRIENDS: "친구 공개", PRIVATE: "나만 보기" } as const;

export default function PhotoPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const [p, setP] = useState<PhotoDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [retrying, setRetrying] = useState(false);
  // 변환 중이면 끝날 때까지 1.5초마다 다시 확인 (최대 약 2분)
  const tick = useRefreshWhile(p?.status === "PROCESSING", 1500, 80);

  useEffect(() => { api<PhotoDetail>(`/photos/${id}`).then(setP).catch((e) => setErr(errorMessage(e))); }, [id, tick]);

  async function onAdminDelete() {
    if (!confirm("관리자 권한으로 이 사진을 삭제할까요? (신고 처리 등) 되돌릴 수 없습니다.")) return;
    setDeleting(true);
    try { await api(`/admin/photos/${id}`, { method: "DELETE" }); router.push("/"); }
    catch (e) { setErr(errorMessage(e)); setDeleting(false); }
  }

  async function onRetry() {
    setRetrying(true);
    try { setP(await api<PhotoDetail>(`/photos/${id}/retry`, { method: "POST" })); }
    catch (e) { setErr(errorMessage(e)); }
    finally { setRetrying(false); }
  }

  async function onDelete() {
    if (!confirm("이 사진을 삭제할까요? 되돌릴 수 없습니다.")) return;
    setDeleting(true);
    try { await api(`/photos/${id}`, { method: "DELETE" }); router.push(`/users/${p!.owner.username}`); }
    catch (e) { setErr(errorMessage(e)); setDeleting(false); }
  }

  if (err) return <ErrorState message={err} />;
  if (!p) return <p className="muted center">불러오는 중…</p>;
  const exif = [p.camera, p.lens, p.focal_length && `${p.focal_length}mm`, p.aperture && `f/${p.aperture}`, p.shutter_speed && `${p.shutter_speed}s`, p.iso && `ISO ${p.iso}`].filter(Boolean);

  return (
    <article className="photo-detail">
      {photoStatus(p) === "READY" ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={p.display_url} alt={p.caption || `${p.place.name}에서 찍은 사진`} width={p.width} height={p.height} />
      ) : p.status === "PROCESSING" ? (
        <div className="photo-placeholder large" role="status">사진을 변환하는 중입니다… 잠시만 기다려 주세요.</div>
      ) : (
        <div className="photo-placeholder large failed" role="alert">
          <p>사진을 변환하지 못했습니다.</p>
          {p.processing_error && <p className="muted">{p.processing_error}</p>}
          {p.is_owner && <button className="btn" onClick={onRetry} disabled={retrying}>{retrying ? "다시 시도하는 중…" : "다시 시도"}</button>}
        </div>
      )}
      <div className="card stack">
        <p><Link href={`/users/${p.owner.username}`} className="user-chip"><Avatar user={p.owner} size={32} /><span><strong>{p.owner.display_name}</strong> <span className="muted">@{p.owner.username}</span></span></Link></p>
        {p.caption && <p className="caption">{p.caption}</p>}
        <p>📍 <Link href={`/places/${p.place.id}`}>{p.place.name}</Link>
          {p.shot_latitude !== null && <span className="muted"> · 촬영 위치 {p.shot_latitude.toFixed(5)}, {p.shot_longitude!.toFixed(5)}</span>}</p>
        <p className="muted">{formatDate(p.taken_at, p.taken_timezone)}</p>
        {exif.length > 0 && <p className="muted">{exif.join(" · ")}</p>}
        {p.is_owner && (
          <div className="actions">
            <span className="badge">{VIS[p.visibility]}</span>
            <Link className="btn" href={`/photos/${p.id}/edit`}>수정</Link>
            {p.original_url && <a className="btn" href={p.original_url} download>원본</a>}
            <button className="btn danger" onClick={onDelete} disabled={deleting}>삭제</button>
          </div>
        )}
        {!p.is_owner && user?.is_admin && (
          <div className="actions"><button className="btn danger" onClick={onAdminDelete} disabled={deleting}>관리자 삭제</button></div>
        )}
      </div>
    </article>
  );
}
