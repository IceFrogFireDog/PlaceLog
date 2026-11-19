"use client";
import type { Visibility } from "@/lib/types";

const OPTIONS: { value: Visibility; label: string; desc: string }[] = [
  { value: "PRIVATE", label: "나만 보기", desc: "나에게만 보입니다." },
  { value: "FRIENDS", label: "친구 공개", desc: "수락한 친구와 나에게 보입니다." },
  { value: "PUBLIC", label: "전체 공개", desc: "로그인하지 않은 사람을 포함해 모두에게 보입니다." },
];

export function VisibilitySelector({ value, onChange }: { value: Visibility; onChange: (v: Visibility) => void }) {
  return (
    <fieldset className="visibility">
      <legend>공개범위</legend>
      {OPTIONS.map((o) => (
        <label key={o.value} className={value === o.value ? "selected" : ""}>
          <input type="radio" name="visibility" value={o.value} checked={value === o.value} onChange={() => onChange(o.value)} />
          <strong>{o.label}</strong>
          <span className="muted">{o.desc}</span>
        </label>
      ))}
    </fieldset>
  );
}
