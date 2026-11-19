"use client";
import type { MapMode } from "@/lib/types";

const MODES: { v: MapMode; label: string; auth: boolean }[] = [
  { v: "WORLD", label: "전체", auth: false },
  { v: "FRIENDS", label: "친구", auth: true },
  { v: "ME", label: "나", auth: true },
];

export function MapFilters({ mode, onChange, loggedIn }: { mode: MapMode; onChange: (m: MapMode) => void; loggedIn: boolean }) {
  return (
    <div className="map-filters" role="tablist" aria-label="지구본 필터">
      {MODES.map((m) => (
        <button key={m.v} role="tab" aria-selected={mode === m.v} className={mode === m.v ? "active" : ""} disabled={m.auth && !loggedIn}
          title={m.auth && !loggedIn ? "로그인이 필요합니다" : undefined} onClick={() => onChange(m.v)}>
          {m.label}
        </button>
      ))}
    </div>
  );
}
