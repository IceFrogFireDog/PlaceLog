"use client";
import dynamic from "next/dynamic";
import { useEffect, useState, useSyncExternalStore } from "react";
import type { GlobeView, MapItem } from "@/lib/types";
import type { SceneProps } from "./GlobeScene";

// SSR에서 window/WebGL을 쓰지 않도록 클라이언트 전용 로드
const GlobeScene = dynamic(() => import("./GlobeScene"), { ssr: false, loading: () => <div className="globe-canvas center muted">지구본 준비 중…</div> });

/** 서버 PLACE_ZOOM과 같은 값. 이 이상이면 클러스터 없이 개별 장소가 온다. */
const LIST_ZOOM = 6;

type Props = Omit<SceneProps, "onError"> & { onViewChange: (v: GlobeView) => void };

// WebGL 지원 여부는 브라우저에서만 알 수 있다. 서버 렌더·하이드레이션 중에는 null(준비 중)로 두어 불일치를 막는다.
let webglCache: boolean | null = null;
const webglSnapshot = () => (webglCache ??= hasWebGL());
const noSubscribe = () => () => {};

export function Globe(props: Props) {
  const supported = useSyncExternalStore(noSubscribe, webglSnapshot, () => null);
  const [failed, setFailed] = useState(false); // WebGL 컨텍스트 생성 실패 등
  const mode = supported === null ? "pending" : supported && !failed ? "globe" : "list";

  const { onViewChange } = props;
  useEffect(() => {
    // 목록 모드에서는 클러스터를 클릭해도 확대할 수 없으므로 개별 장소 수준으로 요청
    if (mode === "list") onViewChange({ bbox: null, zoom: LIST_ZOOM });
  }, [mode, onViewChange]);

  if (mode === "pending") return <div className="globe-canvas center muted">지구본 준비 중…</div>;
  if (mode === "list") return <FallbackList items={props.items} onSelect={props.onSelect} />;
  return <GlobeScene {...props} onError={() => setFailed(true)} />;
}

function hasWebGL(): boolean {
  try {
    const c = document.createElement("canvas");
    const gl = c.getContext("webgl2") || c.getContext("webgl");
    (gl as WebGLRenderingContext | null)?.getExtension("WEBGL_lose_context")?.loseContext(); // 검사용 컨텍스트 즉시 반환
    return !!gl;
  } catch {
    return false;
  }
}

function FallbackList({ items, onSelect }: { items: MapItem[]; onSelect: (i: MapItem) => void }) {
  return (
    <div className="card fallback">
      <p className="muted">이 기기에서는 지구본(WebGL)을 표시할 수 없어 장소 목록으로 보여 드립니다.</p>
      {items.length === 0 ? <p className="muted">볼 수 있는 장소가 없습니다.</p> : (
        <ul className="list">
          {items.map((i) => (
            <li key={i.kind === "place" ? i.place_id : i.id}>
              <button className="link" onClick={() => onSelect(i)}>{i.kind === "place" ? i.name : i.label} · 사진 {i.photo_count}</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
