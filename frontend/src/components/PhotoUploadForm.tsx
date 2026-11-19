"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { heicTiff } from "@/lib/heicExif";
import type { PhotoDetail, Place, Visibility } from "@/lib/types";
import { localOffset, OFFSETS, validLatLng } from "@/lib/validation";
import { useAuth } from "./AuthProvider";
import { LocationPicker } from "./LocationPicker";
import { VisibilitySelector } from "./VisibilitySelector";

const MAX_BYTES = 20 * 1024 * 1024; // 서버 MAX_UPLOAD_BYTES와 맞출 것 (최종 검사는 서버)
const MAX_RAW_BYTES = 80 * 1024 * 1024; // 서버 MAX_RAW_UPLOAD_BYTES
const MAX_FILES = 20;
const TYPES = ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"];
// 카메라 RAW: 브라우저는 그리지 못하므로 미리보기 없이 올리고, 서버가 LibRaw로 변환한다
const RAW_EXTS = [".dng", ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srw", ".orf", ".rw2", ".raf", ".pef"];
const EXTS = [".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ...RAW_EXTS];
// 윈도우 등에서는 HEIC의 MIME이 비어 있으므로 확장자도 허용한다. 실제 형식은 서버가 파일 내용으로 판별한다.
const ACCEPT = [...TYPES, ...EXTS].join(",");

/** unreadable: 브라우저에서 사진 정보를 읽지 못함 → 서버가 EXIF를 읽어 쓰게 맡긴다 */
interface Exif { lat: number | null; lng: number | null; takenLocal: string | null; offset: string | null; unreadable: boolean }
type Status = "ready" | "uploading" | "done" | "error";
interface Item {
  key: string; file: File; url: string;
  exif: Exif | null; // null = 읽는 중
  noPreview: boolean; caption: string; status: Status; error?: string; photoId?: string;
}

const fileKey = (f: File) => `${f.name}:${f.size}:${f.lastModified}`;
const allowed = (f: File) => TYPES.includes(f.type) || EXTS.some((e) => f.name.toLowerCase().endsWith(e));
const isHeic = (f: File) => /^image\/hei[cf]$/.test(f.type) || /\.hei[cf]$/i.test(f.name);
const isRaw = (f: File) => RAW_EXTS.some((e) => f.name.toLowerCase().endsWith(e));

// pick 옵션을 쓰면 GPS 원본 태그가 빠져 위경도 계산이 안 되므로 필요한 블록만 지정
const EXIF_OPTS = { tiff: true, exif: true, gps: true, ifd1: false, xmp: false, icc: false, iptc: false, reviveValues: false };

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function toExif(d: any): Exif {
  const gps = validLatLng(d.latitude, d.longitude);
  const raw: unknown = d.DateTimeOriginal;
  const off: unknown = d.OffsetTimeOriginal;
  return {
    lat: gps ? d.latitude : null,
    lng: gps ? d.longitude : null,
    takenLocal: typeof raw === "string" && /^\d{4}:\d{2}:\d{2} \d{2}:\d{2}/.test(raw) ? raw.slice(0, 16).replace(/^(\d{4}):(\d{2}):(\d{2}) /, "$1-$2-$3T") : null,
    offset: typeof off === "string" && /^[+-]\d{2}:\d{2}$/.test(off) ? off : null,
    unreadable: false,
  };
}

async function readExif(f: File): Promise<Exif> {
  const none: Exif = { lat: null, lng: null, takenLocal: null, offset: null, unreadable: false };
  let exifr;
  try { exifr = (await import("exifr")).default; } catch { return { ...none, unreadable: true }; }
  let failed = false;
  try {
    const d = await exifr.parse(f, EXIF_OPTS);
    if (d) {
      const r = toExif(d);
      if (r.lat !== null || r.takenLocal !== null || !d.errors?.length) return r;
    }
    failed = !!d?.errors?.length;
  } catch {
    failed = true;
  }
  if (isHeic(f)) {
    // exifr이 못 읽는 HEIC(base_offset을 쓰는 파일)는 EXIF 부분만 꺼내 다시 읽는다
    const tiff = await heicTiff(f);
    if (tiff) {
      try {
        const d = await exifr.parse(tiff, EXIF_OPTS);
        if (d && !d.errors?.length) return toExif(d);
      } catch { /* 아래에서 서버에 맡김 */ }
    }
    failed = true;
  }
  return { ...none, unreadable: failed };
}

function summary(e: Exif | null): string {
  if (!e) return "사진 정보 읽는 중…";
  if (e.unreadable) return "브라우저에서 사진 정보를 읽지 못했습니다 · 올린 뒤 서버가 GPS·촬영일을 찾아 씁니다";
  const gps = e.lat !== null ? "GPS 있음" : "GPS 없음";
  const date = e.takenLocal ? `${e.takenLocal.replace("T", " ")}${e.offset ? ` (UTC${e.offset})` : " (시간대 없음)"}` : "촬영일 없음";
  return `${gps} · ${date}`;
}

const errText = (err: unknown) => {
  if (!(err instanceof ApiError)) return "업로드에 실패했습니다. 네트워크를 확인해 주세요.";
  const fields = Object.values(err.fieldErrors);
  return fields.length ? `${err.message} (${fields.join(", ")})` : err.message;
};

export function PhotoUploadForm() {
  const router = useRouter();
  const { user } = useAuth();
  const [items, setItems] = useState<Item[]>([]);
  const [rejected, setRejected] = useState<string[]>([]);
  const [place, setPlace] = useState<Place | null>(null);
  // 사용자가 직접 고친 값. null이면 (한 장일 때) 사진의 EXIF 값을 보여 준다.
  const [shotManual, setShotManual] = useState<{ lat: string; lng: string } | null>(null);
  const [takenManual, setTakenManual] = useState<{ local: string; offset: string } | null>(null);
  const [fallbackOffset, setFallbackOffset] = useState(localOffset());
  const [caption, setCaption] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("PRIVATE");
  const [shareExact, setShareExact] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  // 미리보기 주소 정리 (화면을 떠날 때)
  const urls = useRef(new Set<string>());
  useEffect(() => {
    const set = urls.current;
    return () => { set.forEach((u) => URL.revokeObjectURL(u)); set.clear(); };
  }, []);

  // 올리는 중에 창을 닫으려 하면 경고
  useEffect(() => {
    if (!submitting) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [submitting]);

  const single = items.length === 1 ? items[0] : null;
  const multi = items.length > 1;
  const singleExif = single?.exif ?? null;
  const fromFileShot = singleExif && singleExif.lat !== null && singleExif.lng !== null
    ? { lat: singleExif.lat.toFixed(6), lng: singleExif.lng.toFixed(6) } : null;
  const shot = shotManual ?? (single ? fromFileShot : null) ?? { lat: "", lng: "" };
  const fromFileTaken = singleExif?.takenLocal ? { local: singleExif.takenLocal, offset: singleExif.offset ?? localOffset() } : null;
  const taken = takenManual ?? (single ? fromFileTaken : null) ?? { local: "", offset: localOffset() };
  const tzUnknown = !takenManual && !!singleExif?.takenLocal && !singleExif.offset;
  const noOffsetCount = multi ? items.filter((i) => i.exif?.takenLocal && !i.exif.offset).length : 0;
  const noGpsCount = multi ? items.filter((i) => i.exif && !i.exif.unreadable && i.exif.lat === null).length : 0;
  const firstGps = items.find((i) => i.exif?.lat != null && i.exif?.lng != null)?.exif;
  const nearHint = firstGps ? { lat: firstGps.lat!, lng: firstGps.lng! } : null;
  const reading = items.some((i) => i.exif === null);
  const pending = items.filter((i) => i.status !== "done");
  const unverified = user?.email_verified === false;

  function patch(key: string, p: Partial<Item>) {
    setItems((prev) => prev.map((i) => (i.key === key ? { ...i, ...p } : i)));
  }

  function addFiles(list: FileList | null) {
    if (!list || !list.length) return;
    setError(null);
    const bad: string[] = [];
    const fresh: Item[] = [];
    const seen = new Set(items.map((i) => i.key));
    for (const f of Array.from(list)) {
      const key = fileKey(f);
      if (seen.has(key)) continue;
      if (!allowed(f)) { bad.push(`${f.name}: JPEG·PNG·WebP·HEIC·카메라 RAW만 올릴 수 있습니다.`); continue; }
      const limit = isRaw(f) ? MAX_RAW_BYTES : MAX_BYTES;
      if (f.size > limit) { bad.push(`${f.name}: ${limit / 1024 / 1024}MB 이하 파일만 올릴 수 있습니다.`); continue; }
      if (items.length + fresh.length >= MAX_FILES) { bad.push(`${f.name}: 한 번에 ${MAX_FILES}장까지 올릴 수 있습니다.`); continue; }
      seen.add(key);
      const url = URL.createObjectURL(f);
      urls.current.add(url);
      fresh.push({ key, file: f, url, exif: null, noPreview: false, caption: "", status: "ready" });
    }
    setRejected(bad);
    if (!fresh.length) return;
    setItems((prev) => [...prev, ...fresh]);
    for (const it of fresh) void readExif(it.file).then((exif) => patch(it.key, { exif }));
  }

  function remove(key: string) {
    const it = items.find((i) => i.key === key);
    if (it) { URL.revokeObjectURL(it.url); urls.current.delete(it.url); }
    setItems((prev) => prev.filter((i) => i.key !== key));
    setError(null);
  }

  function formFor(it: Item, placeId: string, hasShot: boolean): FormData {
    const fd = new FormData();
    fd.set("file", it.file);
    fd.set("place_id", placeId);
    fd.set("visibility", visibility);
    fd.set("share_exact_location", String(shareExact));
    if (!multi) {
      // 한 장: 화면에서 사용자가 확인한 값만 보낸다 (비운 칸은 EXIF로 다시 채우지 않음)
      fd.set("caption", caption);
      const serverReads = !!it.exif?.unreadable;
      fd.set("use_exif_location", String(serverReads && !shotManual));
      fd.set("use_exif_date", String(serverReads && !takenManual));
      if (hasShot) { fd.set("shot_latitude", shot.lat.trim()); fd.set("shot_longitude", shot.lng.trim()); }
      if (taken.local) { fd.set("taken_at", `${taken.local.slice(0, 16)}:00${taken.offset}`); fd.set("taken_timezone", taken.offset); }
      return fd;
    }
    // 여러 장: 사진마다 자기 GPS·촬영일을 쓰고, GPS가 없으면 위에 입력한 촬영 좌표를 쓴다
    fd.set("caption", it.caption);
    const ex = it.exif!;
    if (ex.unreadable) {
      fd.set("use_exif_location", "true"); fd.set("use_exif_date", "true");
      return fd;
    }
    if (ex.lat !== null && ex.lng !== null) {
      fd.set("use_exif_location", "false"); fd.set("shot_latitude", ex.lat.toFixed(6)); fd.set("shot_longitude", ex.lng.toFixed(6));
    } else if (hasShot) {
      fd.set("use_exif_location", "false"); fd.set("shot_latitude", shot.lat.trim()); fd.set("shot_longitude", shot.lng.trim());
    } else fd.set("use_exif_location", "true"); // 브라우저가 못 읽은 GPS를 서버가 읽을 수 있으면 사용
    if (ex.takenLocal) {
      const off = ex.offset ?? fallbackOffset;
      fd.set("use_exif_date", "false"); fd.set("taken_at", `${ex.takenLocal}:00${off}`); fd.set("taken_timezone", off);
    } else fd.set("use_exif_date", "true");
    return fd;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setError(null); setFieldErrors({});
    if (!items.length) return setError("사진을 선택해 주세요.");
    if (!pending.length) return;
    if (reading) return setError("사진 정보를 읽는 중입니다. 잠시 후 다시 눌러 주세요.");
    if (!place) return setError("대표 장소를 선택하거나 만들어 주세요.");
    const latSet = shot.lat.trim() !== "", lngSet = shot.lng.trim() !== "";
    if (latSet !== lngSet) return setError("촬영 위도와 경도를 함께 입력하거나 둘 다 비워 주세요.");
    const hasShot = latSet && lngSet;
    if (hasShot && !validLatLng(Number(shot.lat), Number(shot.lng))) return setError("촬영 좌표를 확인해 주세요.");
    if (shareExact && visibility !== "PRIVATE" && !confirm("정확한 촬영 위치가 사진을 볼 수 있는 사람에게 공개됩니다. 계속할까요?")) return;

    setSubmitting(true);
    let failed = 0;
    let lastId: string | null = null;
    let lastErr: string | null = null;
    for (const it of pending) {
      patch(it.key, { status: "uploading", error: undefined });
      try {
        const photo = await api<PhotoDetail>("/photos", { method: "POST", form: formFor(it, place.id, hasShot) });
        lastId = photo.id;
        patch(it.key, { status: "done", photoId: photo.id });
      } catch (err) {
        failed++;
        lastErr = errText(err);
        patch(it.key, { status: "error", error: lastErr });
        if (!multi && err instanceof ApiError) setFieldErrors(err.fieldErrors);
        // 로그인 끊김·인증 필요·장소 문제는 나머지 사진도 똑같이 실패하므로 멈춘다
        if (err instanceof ApiError && [401, 403, 404].includes(err.status)) { setError(err.message); break; }
      }
    }
    setSubmitting(false);
    if (failed === 0) {
      router.push(items.length === 1 && lastId ? `/photos/${lastId}` : `/places/${place.id}`);
    } else {
      setError((prev) => prev ?? (multi ? `${failed}장을 올리지 못했습니다. 이유를 확인하고 다시 시도해 주세요. 이미 올라간 사진은 다시 올리지 않습니다.` : lastErr));
    }
  }

  function shotHint(): string | undefined {
    if (multi) return `여러 장일 때는 사진마다 자기 GPS 좌표를 씁니다. 여기 입력한 촬영 좌표는 GPS가 없는 사진${noGpsCount ? ` ${noGpsCount}장` : ""}에만 쓰이며, 비워 두면 위치 없이 올립니다.`;
    if (!single) return "사진을 고르면 GPS 좌표를 자동으로 채웁니다.";
    if (!shotManual) return singleExif?.unreadable ? "브라우저에서 사진 정보를 읽지 못했습니다. 비워 두면 서버가 사진 속 GPS를 찾아 씁니다." : undefined;
    const empty = !shotManual.lat.trim() && !shotManual.lng.trim();
    if (fromFileShot) return empty ? "촬영 좌표를 비웠습니다. 위치 없이 올립니다." : "직접 고친 좌표를 씁니다.";
    return empty ? "촬영 좌표 없이 올립니다." : "직접 입력한 좌표를 씁니다.";
  }

  const doneCount = items.length - pending.length;
  return (
    <form className="card form" onSubmit={onSubmit}>
      {unverified && <p className="notice" role="status">이메일 인증을 마쳐야 사진을 올릴 수 있습니다. 위 안내에서 인증 메일을 다시 받을 수 있습니다.</p>}
      <label>사진 추가 (JPEG·PNG·WebP·HEIC 장당 20MB · 카메라 RAW 80MB, 한 번에 {MAX_FILES}장까지)
        <input type="file" multiple accept={ACCEPT} disabled={submitting} onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
      </label>
      {rejected.length > 0 && <ul className="error list">{rejected.map((r) => <li key={r}>{r}</li>)}</ul>}

      {items.length > 0 && (
        <ul className={`upload-list${single ? " single" : ""}`} aria-label="올릴 사진">
          {items.map((it) => (
            <li key={it.key} className={`upload-item status-${it.status}`}>
              {it.noPreview ? (
                <div className="thumb placeholder" aria-hidden="true">{isHeic(it.file) ? "HEIC\n미리보기 없음" : isRaw(it.file) ? "RAW\n미리보기 없음" : "미리보기 없음"}</div>
              ) : (
                // 브라우저가 HEIC를 못 그리면(크롬 등) 대체 표시로 바꾼다. 서버가 변환해 저장하므로 업로드에는 문제없다.
                // eslint-disable-next-line @next/next/no-img-element
                <img className="thumb" src={it.url} alt={`${it.file.name} 미리보기`} onError={() => patch(it.key, { noPreview: true })} />
              )}
              <div className="upload-info">
                <strong className="filename" title={it.file.name}>{it.file.name}</strong>
                <span className="muted">{summary(it.exif)}</span>
                {multi && (
                  <input value={it.caption} maxLength={2000} placeholder="설명 (선택)" aria-label={`${it.file.name} 설명`}
                    disabled={submitting || it.status === "done"} onChange={(e) => patch(it.key, { caption: e.target.value })}
                    onKeyDown={(e) => { if (e.key === "Enter") e.preventDefault(); }} />
                )}
                {it.status === "uploading" && <span className="muted" role="status">올리는 중…</span>}
                {it.status === "done" && <span className="ok">완료 · <Link href={`/photos/${it.photoId}`}>보기</Link></span>}
                {it.status === "error" && <span className="error">{it.error}</span>}
              </div>
              {it.status !== "done" && <button type="button" className="link" onClick={() => remove(it.key)} disabled={submitting} aria-label={`${it.file.name} 빼기`}>빼기</button>}
            </li>
          ))}
        </ul>
      )}

      <LocationPicker
        place={place} onPlace={setPlace} shot={shot} onShot={setShotManual} nearHint={nearHint}
        gpsFromExif={single && !shotManual ? !!fromFileShot : undefined}
        shotHint={shotHint()}
        shotAction={single && shotManual && fromFileShot ? { label: "사진 GPS로 되돌리기", onClick: () => setShotManual(null) } : undefined}
      />

      {!multi ? (
        <fieldset>
          <legend>촬영일</legend>
          <div className="row">
            <input type="datetime-local" value={taken.local} aria-label="촬영 일시" onChange={(e) => setTakenManual({ local: e.target.value, offset: taken.offset })} />
            <select value={taken.offset} onChange={(e) => setTakenManual({ local: taken.local, offset: e.target.value })} aria-label="촬영지 시간대">
              {Array.from(new Set([taken.offset, ...OFFSETS])).map((o) => <option key={o} value={o}>UTC{o}</option>)}
            </select>
          </div>
          {tzUnknown && <p className="hint warn">사진에 시간대 정보가 없습니다. 촬영지 시간대를 확인해 주세요.</p>}
          {!taken.local && (singleExif?.unreadable && !takenManual
            ? <p className="hint">브라우저에서 촬영일을 읽지 못했습니다. 비워 두면 서버가 사진 속 촬영일(시간대가 있는 경우)을 찾아 씁니다.</p>
            : <p className="hint">모르면 비워 두세요. 등록일로 대신 채우지 않습니다.</p>)}
          {takenManual && fromFileTaken && <button type="button" className="link" onClick={() => setTakenManual(null)}>사진의 촬영일로 되돌리기</button>}
        </fieldset>
      ) : (
        <fieldset>
          <legend>촬영일</legend>
          <p className="hint">사진마다 EXIF 촬영일을 씁니다. 날짜가 없는 사진은 비워 두며, 올린 뒤 사진별로 고칠 수 있습니다.</p>
          {noOffsetCount > 0 && (
            <label>시간대 정보가 없는 사진 {noOffsetCount}장의 촬영지 시간대
              <select value={fallbackOffset} onChange={(e) => setFallbackOffset(e.target.value)}>
                {Array.from(new Set([fallbackOffset, ...OFFSETS])).map((o) => <option key={o} value={o}>UTC{o}</option>)}
              </select>
            </label>
          )}
        </fieldset>
      )}

      {!multi && (
        <label>설명
          <textarea value={caption} maxLength={2000} rows={3} onChange={(e) => setCaption(e.target.value)} />
          {fieldErrors.caption && <span className="error">{fieldErrors.caption}</span>}
        </label>
      )}

      <VisibilitySelector value={visibility} onChange={setVisibility} />
      <label className="check">
        <input type="checkbox" checked={shareExact} onChange={(e) => setShareExact(e.target.checked)} />
        정확한 촬영 좌표도 공개 (끄면 대표 장소만 보입니다)
      </label>

      {error && <p className="error" role="alert">{error}</p>}
      <button className="btn primary" type="submit" disabled={submitting || unverified || reading}>
        {submitting ? `올리는 중… (${doneCount}/${items.length})` : reading ? "사진 정보 읽는 중…"
          : doneCount > 0 ? `남은 ${pending.length}장 다시 올리기` : items.length > 1 ? `${items.length}장 등록` : "등록"}
      </button>
    </form>
  );
}
