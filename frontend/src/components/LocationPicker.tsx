"use client";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { ApiError, api, errorMessage } from "@/lib/api";
import type { GeoResult, Page, Place, PlaceCreated } from "@/lib/types";
import { validLatLng } from "@/lib/validation";
import type { LatLng } from "./MapPicker";

// Leaflet은 브라우저 전용이고 용량이 커서 지도를 열 때만 불러온다
const MapPicker = dynamic(() => import("./MapPicker").then((m) => m.MapPicker), {
  ssr: false, loading: () => <div className="map-canvas center muted">지도 불러오는 중…</div>,
});

interface Props {
  place: Place | null;
  onPlace: (p: Place | null) => void;
  /** EXIF 또는 수동 입력 촬영 좌표 */
  shot: { lat: string; lng: string };
  onShot: (s: { lat: string; lng: string }) => void;
  /** 업로드 화면에서만 사용. 생략하면 일반 안내 문구 */
  gpsFromExif?: boolean;
  /** 촬영 좌표 안내 문구를 직접 지정 (여러 장 업로드 등) */
  shotHint?: string;
  /** 촬영 좌표가 비어 있을 때 지도 시작 위치·새 장소 좌표 제안에 쓸 위치 (예: 여러 장 중 GPS가 있는 첫 사진) */
  nearHint?: LatLng | null;
  /** 안내 문구 옆에 붙는 추가 동작 (예: 사진 GPS로 되돌리기) */
  shotAction?: { label: string; onClick: () => void };
}

const preventEnter = (e: React.KeyboardEvent) => { if (e.key === "Enter") e.preventDefault(); }; // 바깥 폼이 제출되지 않게

function toLatLng(lat: string, lng: string): LatLng | null {
  if (!lat.trim() || !lng.trim()) return null;
  const v = { lat: Number(lat), lng: Number(lng) };
  return validLatLng(v.lat, v.lng) ? v : null;
}

export function LocationPicker({ place, onPlace, shot, onShot, gpsFromExif, shotHint, nearHint, shotAction }: Props) {
  const [q, setQ] = useState("");
  // 검색어별로 저장: 입력이 바뀌면 이전 결과는 자동으로 숨겨지고 늦게 온 응답도 섞이지 않는다
  const [search, setSearch] = useState<{ q: string; items: Place[]; err: string | null } | null>(null);
  const [shotMap, setShotMap] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  // 새 장소 좌표는 장소를 볼 수 있는 모든 사람에게 공개된다. 촬영 좌표(비공개 가능)와 분리한다.
  const [placeLat, setPlaceLat] = useState("");
  const [placeLng, setPlaceLng] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("");
  const [dup, setDup] = useState<Place | null>(null);
  const [cands, setCands] = useState<Place[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!q.trim()) return;
    const ctl = new AbortController();
    const t = setTimeout(() => {
      api<Page<Place>>("/places", { query: { q, limit: 10 }, signal: ctl.signal })
        .then((r) => setSearch({ q, items: r.items, err: null }))
        .catch((e) => { if ((e as Error).name !== "AbortError") setSearch({ q, items: [], err: errorMessage(e) }); });
    }, 250);
    return () => { clearTimeout(t); ctl.abort(); };
  }, [q]);
  const found = q.trim() && search?.q === q ? search : null;
  const results = found?.items ?? [];
  const searchErr = found?.err ?? null;

  const shotLatLng = toLatLng(shot.lat, shot.lng);
  const placeLatLng = toLatLng(placeLat, placeLng);

  function startCreate() {
    setCreating(true); setNewName(q.trim()); setDup(null); setErr(null);
    setAddress(""); setCity(""); setCountry("");
    // 촬영 좌표를 그대로 쓰면 집 위치 등이 공개될 수 있어 약 1km(소수 둘째 자리) 단위로 반올림해 채운다
    const src = shotLatLng ?? nearHint ?? null;
    setPlaceLat(src ? src.lat.toFixed(2) : ""); setPlaceLng(src ? src.lng.toFixed(2) : "");
  }

  function onGeoResult(r: GeoResult) {
    if (!newName.trim()) setNewName(r.name);
    setAddress(r.address ?? ""); setCity(r.city ?? ""); setCountry(r.country_code ?? "");
  }

  async function fillCityCountry() {
    if (!placeLatLng) return setErr("먼저 장소 좌표를 정해 주세요.");
    setErr(null); setBusy(true);
    try {
      // 주소(도로명)는 개인 장소가 드러날 수 있어 채우지 않고 도시·국가만 채운다
      const r = await api<GeoResult>("/geocode/reverse", { query: { lat: placeLatLng.lat, lng: placeLatLng.lng } });
      setCity(r.city ?? ""); setCountry(r.country_code ?? "");
    } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  }

  async function createPlace(force: boolean) {
    setErr(null);
    if (!newName.trim()) return setErr("장소 이름을 입력해 주세요.");
    if (!placeLat.trim() || !placeLng.trim()) return setErr("새 장소의 위도와 경도를 입력하거나 지도에서 고르세요.");
    if (!placeLatLng) return setErr("좌표를 확인해 주세요. (위도 −90~90, 경도 −180~180)");
    if (country.trim() && !/^[A-Za-z]{2}$/.test(country.trim())) return setErr("국가 코드는 영문 2자입니다. (예: KR)");
    setBusy(true);
    try {
      const p = await api<PlaceCreated>("/places", {
        method: "POST",
        json: {
          name: newName.trim(), latitude: placeLatLng.lat, longitude: placeLatLng.lng, force,
          address: address.trim() || null, city: city.trim() || null, country_code: country.trim() || null,
        },
      });
      setCands(p.nearby_candidates);
      setDup(null);
      onPlace(p);
      setCreating(false);
    } catch (e) {
      const existing = e instanceof ApiError && e.code === "DUPLICATE_PLACE" ? (e.body?.existing_place as Place | undefined) : undefined;
      if (existing) setDup(existing);
      else setErr(errorMessage(e));
    } finally { setBusy(false); }
  }

  const hint = shotHint ?? (gpsFromExif === undefined ? "촬영 좌표를 수정하거나 비워 두세요."
    : gpsFromExif ? "사진의 GPS에서 가져온 좌표입니다. 맞는지 확인해 주세요." : "사진에 GPS가 없습니다. 지도에서 고르거나 직접 입력하거나 비워 두세요.");

  return (
    <fieldset className="location">
      <legend>위치</legend>
      <div className="row">
        <label>촬영 위도<input inputMode="decimal" value={shot.lat} onChange={(e) => onShot({ ...shot, lat: e.target.value })} placeholder="37.5665" /></label>
        <label>촬영 경도<input inputMode="decimal" value={shot.lng} onChange={(e) => onShot({ ...shot, lng: e.target.value })} placeholder="126.9780" /></label>
      </div>
      <p className="hint">{hint}</p>
      <div className="actions">
        <button type="button" className="btn" aria-expanded={shotMap} onClick={() => setShotMap(!shotMap)}>{shotMap ? "지도 닫기" : "지도에서 촬영 위치 고르기"}</button>
        {(shot.lat || shot.lng) && <button type="button" className="link" onClick={() => onShot({ lat: "", lng: "" })}>촬영 좌표 지우기</button>}
        {shotAction && <button type="button" className="link" onClick={shotAction.onClick}>{shotAction.label}</button>}
      </div>
      {shotMap && (
        <MapPicker label="촬영 위치 지도" value={shotLatLng} onChange={(v) => onShot({ lat: v.lat.toFixed(6), lng: v.lng.toFixed(6) })}
          center={place ? { lat: place.latitude, lng: place.longitude } : nearHint ?? null} />
      )}

      <label>대표 장소 {place && <strong>· {place.name}</strong>}</label>
      {place ? (
        <button type="button" className="btn" onClick={() => onPlace(null)}>장소 다시 선택</button>
      ) : (
        <>
          <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={preventEnter} placeholder="기존 장소 검색" aria-label="기존 장소 검색" />
          {results.length > 0 && (
            <ul className="list">
              {results.map((p) => (
                <li key={p.id}><button type="button" className="link" onClick={() => onPlace(p)}>{p.name} <span className="muted">{p.city ?? ""} {p.latitude.toFixed(3)}, {p.longitude.toFixed(3)}</span></button></li>
              ))}
            </ul>
          )}
          {!creating ? (
            <button type="button" className="btn" onClick={startCreate}>새 장소 만들기</button>
          ) : (
            <div className="new-place">
              <input value={newName} onChange={(e) => { setNewName(e.target.value); setDup(null); }} onKeyDown={preventEnter} placeholder="새 장소 이름" aria-label="새 장소 이름" maxLength={120} />
              <MapPicker label="새 장소 위치 지도" value={placeLatLng} center={shotLatLng ?? nearHint ?? null} onResult={onGeoResult}
                onChange={(v) => { setPlaceLat(v.lat.toFixed(5)); setPlaceLng(v.lng.toFixed(5)); setDup(null); }} />
              <div className="row">
                <label>장소 위도<input inputMode="decimal" value={placeLat} onChange={(e) => { setPlaceLat(e.target.value); setDup(null); }} onKeyDown={preventEnter} /></label>
                <label>장소 경도<input inputMode="decimal" value={placeLng} onChange={(e) => { setPlaceLng(e.target.value); setDup(null); }} onKeyDown={preventEnter} /></label>
              </div>
              <div className="row">
                <label>도시 (선택)<input value={city} maxLength={120} onChange={(e) => setCity(e.target.value)} onKeyDown={preventEnter} /></label>
                <label>국가 코드 (선택)<input value={country} maxLength={2} placeholder="KR" onChange={(e) => setCountry(e.target.value.toUpperCase())} onKeyDown={preventEnter} /></label>
              </div>
              <label>주소 (선택)<input value={address} maxLength={300} onChange={(e) => setAddress(e.target.value)} onKeyDown={preventEnter} /></label>
              <button type="button" className="btn" onClick={fillCityCountry} disabled={busy || !placeLatLng}>이 좌표로 도시·국가 채우기</button>
              <p className="hint warn">장소 이름·좌표·주소는 이 장소의 사진을 볼 수 있는 사람에게 공개됩니다. 촬영 좌표에서 채운 값은 약 1km 단위로 반올림했습니다. 집 등 개인 장소는 정확한 좌표나 주소를 넣지 마세요.</p>
              {dup && (
                <div className="notice" role="alert">
                  <p>근처에 같은 이름의 장소 <strong>{dup.name}</strong>이(가) 이미 있습니다. 같은 곳이면 기존 장소를 쓰면 사진이 한곳에 모입니다.</p>
                  <div className="actions">
                    <button type="button" className="btn primary" onClick={() => { onPlace(dup); setDup(null); setCreating(false); }}>이 장소 사용</button>
                    <button type="button" className="btn" onClick={() => void createPlace(true)} disabled={busy}>그래도 새로 만들기</button>
                  </div>
                </div>
              )}
              <div className="actions">
                <button type="button" className="btn primary" onClick={() => void createPlace(false)} disabled={busy}>{busy ? "처리 중…" : "생성"}</button>
                <button type="button" className="link" onClick={() => { setCreating(false); setDup(null); setErr(null); }}>취소</button>
              </div>
            </div>
          )}
        </>
      )}
      {cands.length > 0 && place && <p className="hint">근처에 비슷한 장소가 있습니다: {cands.map((c) => c.name).join(", ")}</p>}
      {searchErr && <p className="error">장소 검색 실패: {searchErr}</p>}
      {err && <p className="error">{err}</p>}
    </fieldset>
  );
}
