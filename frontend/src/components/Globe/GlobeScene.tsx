"use client";
/**
 * Three.js 지구본 어댑터. 지구본 라이브러리 관련 코드는 이 파일에만 둔다.
 * 해안선: world-atlas (Natural Earth 1:110m, 확대하면 1:50m. 퍼블릭 도메인 데이터 / ISC 패키지)
 */
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { mesh } from "topojson-client";
import type { GeometryCollection, Topology } from "topojson-specification";
import type { GlobeView, MapItem } from "@/lib/types";

export interface SceneProps {
  items: MapItem[];
  selectedId: string | null;
  /** zoomIn=true면 현재보다 확대(클러스터), 아니면 적당한 거리로 이동(검색) */
  focus: { lat: number; lng: number; seq: number; zoomIn?: boolean } | null;
  onSelect: (item: MapItem) => void;
  onViewChange: (v: GlobeView) => void;
  onError: () => void;
}

const R = 1;
const MIN_D = 1.01, MAX_D = 4; // 최소 거리를 낮춰 도시 안 장소들도 구분되게
const DETAIL_D = 1.7; // 카메라가 이보다 가까우면 1:50m 해안선으로 바꾼다

function coastline(topo: Topology<{ land: GeometryCollection }>): THREE.LineSegments {
  const m = mesh(topo, topo.objects.land);
  const pos: number[] = [];
  for (const line of m.coordinates) for (let i = 0; i < line.length - 1; i++) {
    pos.push(...latLngToVec3(line[i][1], line[i][0], R * 1.002).toArray(), ...latLngToVec3(line[i + 1][1], line[i + 1][0], R * 1.002).toArray());
  }
  const g = new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  return new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0x8fd3ff }));
}

const asTopo = (mod: unknown) => ((mod as { default?: unknown }).default ?? mod) as Topology<{ land: GeometryCollection }>;

function tooltipText(it: MapItem): string {
  return it.kind === "place" ? `${it.name} · 사진 ${it.photo_count}장` : `${it.label} · 장소 ${it.place_count}곳 · 사진 ${it.photo_count}장`;
}

export function latLngToVec3(lat: number, lng: number, r = R): THREE.Vector3 {
  const phi = THREE.MathUtils.degToRad(90 - lat);
  const theta = THREE.MathUtils.degToRad(lng + 180);
  return new THREE.Vector3(-r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta));
}

export function vec3ToLatLng(v: THREE.Vector3): { lat: number; lng: number } {
  const n = v.clone().normalize();
  const lat = 90 - THREE.MathUtils.radToDeg(Math.acos(n.y));
  let lng = THREE.MathUtils.radToDeg(Math.atan2(n.z, -n.x)) - 180;
  if (lng < -180) lng += 360;
  return { lat, lng };
}

function distanceToZoom(d: number): number {
  return Math.max(0, Math.min(20, Math.round(Math.log2(3 / (d - 1)) * 1.8)));
}

function computeView(camera: THREE.PerspectiveCamera): GlobeView {
  const d = camera.position.length();
  const zoom = distanceToZoom(d);
  const { lat, lng } = vec3ToLatLng(camera.position);
  const half = THREE.MathUtils.radToDeg(Math.acos(R / d)) * 1.1; // 보이는 반구 반각
  if (half >= 60) return { bbox: null, zoom };
  const s = Math.max(-90, lat - half), n = Math.min(90, lat + half);
  if (n >= 89 || s <= -89) return { bbox: null, zoom };
  const dLng = Math.min(180, half / Math.max(0.15, Math.cos(THREE.MathUtils.degToRad(lat))));
  if (dLng >= 180) return { bbox: [-180, s, 180, n], zoom };
  const wrap = (x: number) => ((x + 540) % 360) - 180;
  return { bbox: [wrap(lng - dLng), s, wrap(lng + dLng), n], zoom }; // west > east면 날짜변경선 걸침
}

export default function GlobeScene({ items, selectedId, focus, onSelect, onViewChange, onError }: SceneProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const stateRef = useRef<{
    scene: THREE.Scene; camera: THREE.PerspectiveCamera; controls: OrbitControls; pins: THREE.Group; animTo: THREE.Vector3 | null;
    /** 핀이 바뀌면 툴팁을 다시 계산 */
    pinsChanged: boolean;
  } | null>(null);
  const cbRef = useRef({ onSelect, onViewChange });
  useEffect(() => { cbRef.current = { onSelect, onViewChange }; });

  // 씬 생성·해제
  useEffect(() => {
    const host = hostRef.current!;
    const tip = tipRef.current!;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      onError();
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(host.clientWidth, host.clientHeight);
    host.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, host.clientWidth / host.clientHeight, 0.01, 100);
    camera.position.copy(latLngToVec3(30, 127, 2.8)); // 동아시아에서 시작

    const globe = new THREE.Mesh(new THREE.SphereGeometry(R, 64, 64), new THREE.MeshBasicMaterial({ color: 0x0f2a44 }));
    scene.add(globe);

    // 위경도 격자
    const grid: number[] = [];
    for (let lat = -60; lat <= 60; lat += 30) for (let lng = -180; lng < 180; lng += 3) grid.push(...latLngToVec3(lat, lng, R * 1.001).toArray(), ...latLngToVec3(lat, lng + 3, R * 1.001).toArray());
    for (let lng = -180; lng < 180; lng += 30) for (let lat = -90; lat < 90; lat += 3) grid.push(...latLngToVec3(lat, lng, R * 1.001).toArray(), ...latLngToVec3(lat + 3, lng, R * 1.001).toArray());
    const gridGeo = new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(grid, 3));
    scene.add(new THREE.LineSegments(gridGeo, new THREE.LineBasicMaterial({ color: 0x1d4a70, transparent: true, opacity: 0.6 })));

    // 해안선 (비동기 로드). 상세 해안선은 처음 확대했을 때만 불러온다.
    let disposed = false;
    let coastCoarse: THREE.LineSegments | null = null;
    let coastDetail: THREE.LineSegments | null = null;
    let detailRequested = false;
    import("world-atlas/land-110m.json").then((mod) => {
      if (disposed) return;
      coastCoarse = coastline(asTopo(mod));
      scene.add(coastCoarse);
    }).catch(() => {});
    const loadDetail = () => {
      detailRequested = true;
      import("world-atlas/land-50m.json").then((mod) => {
        if (disposed) return;
        coastDetail = coastline(asTopo(mod));
        scene.add(coastDetail);
      }).catch(() => {});
    };

    const pins = new THREE.Group();
    scene.add(pins);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enablePan = false;
    controls.enableDamping = true;
    controls.minDistance = MIN_D;
    controls.maxDistance = MAX_D;
    controls.rotateSpeed = 0.5;
    controls.zoomSpeed = 0.8;
    const emitView = () => cbRef.current.onViewChange(computeView(camera));
    // 카메라가 움직이는 동안(관성 포함) change가 계속 발생 → 멈춘 뒤 250ms 지나면 최종 범위로 조회
    let settleTimer: ReturnType<typeof setTimeout> | undefined;
    let hoverDirty = false;
    const onChange = () => { clearTimeout(settleTimer); settleTimer = setTimeout(emitView, 250); hoverDirty = true; };
    controls.addEventListener("change", onChange);
    emitView();

    stateRef.current = { scene, camera, controls, pins, animTo: null, pinsChanged: false };

    // 화면 좌표 → 앞쪽(보이는) 핀. 지구 뒤에 가려진 핀은 고르지 않는다.
    const ray = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    const pick = (x: number, y: number, rect: DOMRect): MapItem | null => {
      ndc.set((x / rect.width) * 2 - 1, -(y / rect.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const hit = ray.intersectObjects(pins.children.filter((c) => c.visible), false)[0];
      const globeHit = ray.intersectObject(globe, false)[0];
      return hit && (!globeHit || hit.distance <= globeHit.distance + 0.02) ? (hit.object.userData.item as MapItem) : null;
    };

    // 클릭(드래그 제외) → 핀 선택
    let down: { x: number; y: number } | null = null;
    const onDown = (e: PointerEvent) => { down = { x: e.clientX, y: e.clientY }; hoverDirty = true; };
    const onUp = (e: PointerEvent) => {
      const d0 = down;
      down = null;
      hoverDirty = true;
      if (!d0 || Math.hypot(e.clientX - d0.x, e.clientY - d0.y) > 5) return;
      const rect = renderer.domElement.getBoundingClientRect();
      const item = pick(e.clientX - rect.left, e.clientY - rect.top, rect);
      if (item) cbRef.current.onSelect(item);
    };
    const onCancel = () => { down = null; hoverDirty = true; };

    // 마우스를 핀 위에 올리면 이름·사진 수 툴팁 (터치에서는 누르면 바로 선택되므로 표시하지 않음)
    let hover: { x: number; y: number } | null = null;
    const onMove = (e: PointerEvent) => {
      if (e.pointerType !== "mouse") return;
      const rect = renderer.domElement.getBoundingClientRect();
      hover = { x: e.clientX - rect.left, y: e.clientY - rect.top };
      hoverDirty = true;
    };
    const onLeave = () => { hover = null; hoverDirty = true; };
    const updateHover = () => {
      const rect = renderer.domElement.getBoundingClientRect();
      const item = hover && !down ? pick(hover.x, hover.y, rect) : null;
      renderer.domElement.style.cursor = item ? "pointer" : "";
      if (!item || !hover) { tip.hidden = true; return; }
      tip.textContent = tooltipText(item); // 사용자 입력(장소 이름)이므로 textContent로만 넣는다
      tip.style.left = `${hover.x}px`;
      tip.style.top = `${hover.y}px`;
      // 오른쪽 가장자리에서는 커서 왼쪽에 띄워 화면 밖으로 나가지 않게
      tip.style.transform = hover.x > rect.width * 0.6 ? "translate(calc(-100% - 12px), -50%)" : "translate(12px, -50%)";
      tip.hidden = false;
    };
    const el = renderer.domElement;
    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointerup", onUp);
    el.addEventListener("pointercancel", onCancel);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);

    const ro = new ResizeObserver(() => {
      camera.aspect = host.clientWidth / Math.max(1, host.clientHeight);
      camera.updateProjectionMatrix();
      renderer.setSize(host.clientWidth, host.clientHeight);
    });
    ro.observe(host);

    let raf = 0;
    const camDir = new THREE.Vector3();
    const tick = () => {
      raf = requestAnimationFrame(tick);
      const st = stateRef.current!;
      if (st.animTo) {
        camera.position.lerp(st.animTo, 0.08);
        if (camera.position.distanceTo(st.animTo) < 0.005) { st.animTo = null; onChange(); }
      }
      controls.update();
      camDir.copy(camera.position).normalize();
      // 핀 크기를 표면까지 거리에 비례시켜 화면상 크기를 일정하게 유지 (확대해도 핀이 겹쳐 뭉치지 않게)
      const scale = Math.max(0.01, camera.position.length() - R);
      for (const p of pins.children) {
        p.visible = p.position.clone().normalize().dot(camDir) > 0.1; // 뒤쪽 핀 숨김
        p.scale.setScalar(scale * (p.userData.baseScale as number));
      }
      const dist = camera.position.length();
      if (dist < DETAIL_D && !detailRequested) loadDetail();
      if (coastDetail) {
        coastDetail.visible = dist < DETAIL_D;
        if (coastCoarse) coastCoarse.visible = !coastDetail.visible;
      }
      if (st.pinsChanged) { st.pinsChanged = false; hoverDirty = true; }
      if (hoverDirty) { hoverDirty = false; updateHover(); }
      renderer.render(scene, camera);
    };
    tick();

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      clearTimeout(settleTimer);
      controls.removeEventListener("change", onChange);
      ro.disconnect();
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointerup", onUp);
      el.removeEventListener("pointercancel", onCancel);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
      tip.hidden = true;
      controls.dispose();
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        m.geometry?.dispose();
        const mat = m.material as THREE.Material | THREE.Material[] | undefined;
        if (Array.isArray(mat)) mat.forEach((x) => x.dispose()); else mat?.dispose();
      });
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
      stateRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 핀 갱신
  useEffect(() => {
    const st = stateRef.current;
    if (!st) return;
    for (const c of [...st.pins.children]) {
      st.pins.remove(c);
      (c as THREE.Mesh).geometry.dispose();
      ((c as THREE.Mesh).material as THREE.Material).dispose();
    }
    for (const it of items) {
      const id = it.kind === "place" ? it.place_id : it.id;
      const selected = id === selectedId;
      const base = it.kind === "cluster" ? 0.014 + Math.min(0.012, Math.log10(it.photo_count + 1) * 0.006) : 0.009;
      const color = selected ? 0xffd166 : it.kind === "cluster" ? 0xff7a59 : 0x4ade80;
      const m = new THREE.Mesh(new THREE.SphereGeometry(1, 12, 12), new THREE.MeshBasicMaterial({ color }));
      m.position.copy(latLngToVec3(it.latitude, it.longitude, R * 1.005));
      m.userData = { item: it, baseScale: selected ? base * 1.5 : base };
      st.pins.add(m);
    }
    st.pinsChanged = true;
  }, [items, selectedId]);

  // 특정 좌표로 이동 (검색·클러스터 확대)
  useEffect(() => {
    const st = stateRef.current;
    if (!st || !focus) return;
    const cur = st.camera.position.length();
    const d = focus.zoomIn
      ? Math.max(MIN_D + 0.02, R + (cur - R) * 0.4) // 표면까지 거리를 40%로 → 확대 수준이 확실히 올라감
      : Math.max(MIN_D + 0.05, Math.min(cur, 1.6));
    st.animTo = latLngToVec3(focus.lat, focus.lng, d);
  }, [focus]);

  return (
    <div ref={hostRef} className="globe-canvas" aria-label="지구본. 드래그로 회전, 스크롤로 확대">
      <div ref={tipRef} className="globe-tooltip" role="tooltip" hidden />
    </div>
  );
}
