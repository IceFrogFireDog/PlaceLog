"use client";
import { ErrorState } from "@/components/ErrorState";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { LocationPicker } from "@/components/LocationPicker";
import { RequireAuth } from "@/components/RequireAuth";
import { VisibilitySelector } from "@/components/VisibilitySelector";
import { ApiError, api, errorMessage } from "@/lib/api";
import type { PhotoDetail, Place, Visibility } from "@/lib/types";
import { localOffset, OFFSETS } from "@/lib/validation";

/** ISO(UTC) → 촬영지 오프셋 기준 datetime-local 문자열 */
function toLocalInput(iso: string, offset: string): string {
  const sign = offset.startsWith("-") ? -1 : 1;
  const [h, m] = offset.slice(1).split(":").map(Number);
  const d = new Date(new Date(iso).getTime() + sign * (h * 60 + m) * 60000);
  return d.toISOString().slice(0, 16);
}

function Edit() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [p, setP] = useState<PhotoDetail | null>(null);
  const [caption, setCaption] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("PRIVATE");
  const [place, setPlace] = useState<Place | null>(null);
  const [shot, setShot] = useState({ lat: "", lng: "" });
  const [shareExact, setShareExact] = useState(false);
  const [taken, setTaken] = useState("");
  const [offset, setOffset] = useState(localOffset());
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<PhotoDetail>(`/photos/${id}`).then((d) => {
      if (!d.is_owner) { setErr("작성자만 수정할 수 있습니다."); return; }
      setP(d); setCaption(d.caption); setVisibility(d.visibility); setShareExact(d.share_exact_location);
      setPlace({ id: d.place.id, name: d.place.name, latitude: d.place.latitude, longitude: d.place.longitude, address: null, city: null, country_code: null, created_at: "" });
      setShot({ lat: d.shot_latitude?.toString() ?? "", lng: d.shot_longitude?.toString() ?? "" });
      const off = d.taken_timezone ?? localOffset();
      setOffset(off);
      if (d.taken_at) setTaken(toLocalInput(d.taken_at, off));
    }).catch((e) => setErr(errorMessage(e)));
  }, [id]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!place) return setErr("대표 장소를 선택해 주세요.");
    const latSet = shot.lat.trim() !== "", lngSet = shot.lng.trim() !== "";
    if (latSet !== lngSet) return setErr("촬영 위도와 경도를 함께 입력하거나, 위치를 지우려면 둘 다 비워 주세요.");
    const hasShot = latSet && lngSet;
    const exposesExact = shareExact && hasShot && visibility !== "PRIVATE";
    const wasExposed = p!.share_exact_location && p!.shot_latitude !== null && p!.visibility !== "PRIVATE";
    if (exposesExact && !wasExposed && !confirm("정확한 촬영 위치가 이 사진을 볼 수 있는 사람에게 공개됩니다. 계속할까요?")) return;
    setBusy(true); setErr(null);
    try {
      await api(`/photos/${id}`, {
        method: "PATCH",
        json: {
          caption, visibility, place_id: place.id, share_exact_location: shareExact,
          ...(taken ? { taken_at: `${taken}:00${offset}`, taken_timezone: offset } : { clear_taken_at: true }),
          ...(hasShot ? { shot_latitude: Number(shot.lat), shot_longitude: Number(shot.lng) } : { clear_shot_location: true }),
        },
      });
      router.push(`/photos/${id}`);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message + (Object.values(e.fieldErrors).length ? ` (${Object.values(e.fieldErrors).join(", ")})` : "") : "저장하지 못했습니다.");
      setBusy(false);
    }
  }

  if (err && !p) return <ErrorState message={err} />;
  if (!p) return <p className="muted center">불러오는 중…</p>;
  return (
    <form className="card form narrow" onSubmit={onSubmit}>
      <h1>사진 수정</h1>
      <label>설명<textarea value={caption} maxLength={2000} rows={3} onChange={(e) => setCaption(e.target.value)} /></label>
      <LocationPicker place={place} onPlace={setPlace} shot={shot} onShot={setShot} />
      <fieldset>
        <legend>촬영일</legend>
        <div className="row">
          <input type="datetime-local" value={taken} onChange={(e) => setTaken(e.target.value)} />
          <select value={offset} onChange={(e) => setOffset(e.target.value)}>{Array.from(new Set([offset, ...OFFSETS])).map((o) => <option key={o} value={o}>UTC{o}</option>)}</select>
        </div>
      </fieldset>
      <VisibilitySelector value={visibility} onChange={setVisibility} />
      <label className="check"><input type="checkbox" checked={shareExact} onChange={(e) => setShareExact(e.target.checked)} />정확한 촬영 좌표 공개</label>
      {err && <p className="error">{err}</p>}
      <button className="btn primary" disabled={busy}>{busy ? "저장 중…" : "저장"}</button>
    </form>
  );
}

export default function EditPage() {
  return <RequireAuth keepOnLogout><Edit /></RequireAuth>;
}
