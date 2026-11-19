"use client";
/**
 * 지도에서 좌표 고르기 (Leaflet + 타일 서버).
 * - 지도를 누르거나 핀을 끌면 좌표가 바뀐다.
 * - 주소·장소 검색은 찾기 버튼(또는 Enter)을 눌렀을 때만 요청한다. 공용 Nominatim은 입력 중 자동완성 요청을 금지한다.
 * - 타일 기본값은 OpenStreetMap 공용 타일(소규모·저빈도 이용만 허용). 운영에서는 NEXT_PUBLIC_MAP_TILE_URL로 바꿀 것.
 */
import "leaflet/dist/leaflet.css";
import type * as Leaflet from "leaflet";
import { useEffect, useRef, useState } from "react";
import { ApiError, api, errorMessage } from "@/lib/api";
import type { GeoResult, GeoSearch } from "@/lib/types";

export interface LatLng { lat: number; lng: number }

const TILE_URL = process.env.NEXT_PUBLIC_MAP_TILE_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTRIBUTION = process.env.NEXT_PUBLIC_MAP_ATTRIBUTION
  || '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors';
const DEFAULT_VIEW = { lat: 36.5, lng: 127.8, zoom: 6 }; // 한반도

type LeafletModule = typeof Leaflet;
interface MapState { L: LeafletModule; map: Leaflet.Map; marker: Leaflet.Marker | null }

interface Props {
  value: LatLng | null;
  onChange: (v: LatLng) => void;
  /** 검색 결과를 골랐을 때 (새 장소 이름·도시·국가 미리 채우기용) */
  onResult?: (r: GeoResult) => void;
  /** 값이 없을 때 처음 보여 줄 위치 */
  center?: LatLng | null;
  label: string;
}

export function wrapLatLng(lat: number, lng: number): LatLng {
  const w = ((((lng + 180) % 360) + 360) % 360) - 180;
  return { lat: Math.max(-90, Math.min(90, lat)), lng: w };
}

function syncMarker(st: MapState | null, v: LatLng | null, onDrag: (v: LatLng) => void) {
  if (!st) return;
  if (!v) { st.marker?.remove(); st.marker = null; return; }
  if (!st.marker) {
    const icon = st.L.divIcon({ className: "map-pin", iconSize: [20, 20], iconAnchor: [10, 10] });
    const marker = st.L.marker([v.lat, v.lng], { draggable: true, icon, keyboard: false, title: "끌어서 위치 조정" }).addTo(st.map);
    marker.on("dragend", () => { const p = marker.getLatLng(); onDrag(wrapLatLng(p.lat, p.lng)); });
    st.marker = marker;
  } else st.marker.setLatLng([v.lat, v.lng]);
  if (!st.map.getBounds().contains([v.lat, v.lng])) st.map.panTo([v.lat, v.lng]);
}

export function MapPicker({ value, onChange, onResult, center, label }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapState | null>(null);
  // 지도가 비동기로 준비되는 동안 바뀐 값·콜백도 반영되도록 최신 값을 ref에 둔다
  const latest = useRef({ value, center, onChange, onResult });
  useEffect(() => { latest.current = { value, center, onChange, onResult }; });
  const [loadErr, setLoadErr] = useState(false);

  useEffect(() => {
    let disposed = false;
    let ro: ResizeObserver | null = null;
    const emit = (v: LatLng) => latest.current.onChange(v);
    import("leaflet").then((mod) => {
      const L = ((mod as unknown as { default?: LeafletModule }).default ?? mod) as LeafletModule;
      const host = hostRef.current;
      if (disposed || !host) return;
      const { value: v, center: c } = latest.current;
      const start = v ?? c;
      const map = L.map(host, { worldCopyJump: true, minZoom: 2, maxZoom: 18 })
        .setView(start ? [start.lat, start.lng] : [DEFAULT_VIEW.lat, DEFAULT_VIEW.lng], v ? 15 : c ? 11 : DEFAULT_VIEW.zoom);
      L.tileLayer(TILE_URL, { attribution: TILE_ATTRIBUTION, maxZoom: 19 }).addTo(map);
      map.on("click", (e: Leaflet.LeafletMouseEvent) => emit(wrapLatLng(e.latlng.lat, e.latlng.lng)));
      mapRef.current = { L, map, marker: null };
      ro = new ResizeObserver(() => map.invalidateSize());
      ro.observe(host);
      syncMarker(mapRef.current, latest.current.value, emit);
    }).catch(() => { if (!disposed) setLoadErr(true); });
    return () => {
      disposed = true;
      ro?.disconnect();
      mapRef.current?.map.remove();
      mapRef.current = null;
    };
  }, []);

  // 입력란에서 좌표를 직접 고친 경우에도 핀을 맞춘다
  const lat = value?.lat, lng = value?.lng;
  useEffect(() => {
    syncMarker(mapRef.current, lat === undefined || lng === undefined ? null : { lat, lng }, (v) => latest.current.onChange(v));
  }, [lat, lng]);

  function pick(r: GeoResult) {
    mapRef.current?.map.setView([r.latitude, r.longitude], 16);
    onChange(wrapLatLng(r.latitude, r.longitude));
    onResult?.(r);
  }

  return (
    <div className="map-picker">
      <GeoSearchBox onPick={pick} />
      {loadErr ? <p className="error">지도를 불러오지 못했습니다. 좌표를 직접 입력해 주세요.</p>
        : <div ref={hostRef} className="map-canvas" role="application" aria-label={`${label}. 지도를 누르거나 핀을 끌어 위치를 고르세요.`} />}
    </div>
  );
}

/** 주소·장소 이름 검색. 바깥 업로드 <form> 안에 들어가므로 <form>을 쓰지 않고 Enter를 직접 처리한다. */
function GeoSearchBox({ onPick }: { onPick: (r: GeoResult) => void }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<GeoSearch | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [disabled, setDisabled] = useState(false);

  async function run() {
    const query = q.trim();
    if (!query || busy) return;
    setBusy(true); setErr(null);
    try {
      setRes(await api<GeoSearch>("/geocode/search", { query: { q: query, limit: 5 } }));
    } catch (e) {
      if (e instanceof ApiError && e.code === "GEOCODER_DISABLED") setDisabled(true);
      setErr(errorMessage(e)); setRes(null);
    } finally { setBusy(false); }
  }

  if (disabled) return <p className="hint">{err} 지도를 눌러 고르세요.</p>;
  return (
    <div className="geo-search">
      <div className="row">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="주소·장소 이름으로 찾기 (예: 경복궁)" aria-label="주소·장소 이름 검색"
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void run(); } }} />
        <button type="button" className="btn" onClick={() => void run()} disabled={busy || !q.trim()}>{busy ? "찾는 중…" : "찾기"}</button>
      </div>
      {err && <p className="error">{err}</p>}
      {res && (res.items.length === 0 ? <p className="hint">검색 결과가 없습니다. 지도를 직접 눌러 고르세요.</p> : (
        <ul className="list geo-results">
          {res.items.map((r, i) => (
            <li key={`${r.latitude},${r.longitude},${i}`}>
              <button type="button" className="link" onClick={() => { pick(r); }}>
                {r.name} <span className="muted">{r.address ?? ""}</span>
              </button>
            </li>
          ))}
        </ul>
      ))}
      {res && <p className="hint">검색 데이터: {res.attribution}</p>}
    </div>
  );

  function pick(r: GeoResult) { onPick(r); setRes(null); }
}
