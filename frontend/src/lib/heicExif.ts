/**
 * HEIC/HEIF에서 EXIF(TIFF) 부분만 꺼낸다.
 * exifr 7.1.3은 iloc 상자의 base_offset을 무시해서, libheif 등으로 만든(일부 안드로이드·편집 앱) HEIC의 EXIF를 읽지 못한다.
 * 그런 파일은 여기서 찾은 TIFF 데이터를 exifr에 넘겨 GPS·촬영일을 읽는다. (아이폰 HEIC는 exifr이 바로 읽는다)
 */

interface Box { type: string; start: number; end: number; body: number }

const MAX_META = 4 * 1024 * 1024;

function fourcc(v: DataView, o: number): string {
  return String.fromCharCode(v.getUint8(o), v.getUint8(o + 1), v.getUint8(o + 2), v.getUint8(o + 3));
}

function uint(v: DataView, o: number, n: number): number {
  if (n === 0) return 0;
  if (n === 2) return v.getUint16(o);
  if (n === 4) return v.getUint32(o);
  if (n === 8) return Number(v.getBigUint64(o));
  throw new Error(`size ${n}`);
}

/** v[start, end) 안의 상자들 */
function children(v: DataView, start: number, end: number): Box[] {
  const out: Box[] = [];
  let o = start;
  while (o + 8 <= end) {
    let size = v.getUint32(o);
    const type = fourcc(v, o + 4);
    let body = o + 8;
    if (size === 1) { size = Number(v.getBigUint64(o + 8)); body = o + 16; } else if (size === 0) size = end - o;
    if (size < 8 || o + size > end) break;
    out.push({ type, start: o, end: o + size, body });
    o += size;
  }
  return out;
}

/** 파일 맨 위의 meta 상자를 찾아 그 부분만 읽는다 */
async function readMeta(file: Blob): Promise<{ v: DataView; meta: Box } | null> {
  let o = 0;
  for (let guard = 0; guard < 64 && o + 8 <= file.size; guard++) {
    const h = new DataView(await file.slice(o, o + 16).arrayBuffer());
    let size = h.getUint32(0);
    const type = fourcc(h, 4);
    if (size === 1 && h.byteLength >= 16) size = Number(h.getBigUint64(8));
    else if (size === 0) size = file.size - o;
    if (size < 8) return null;
    if (type === "meta") {
      if (size > MAX_META) return null;
      const v = new DataView(await file.slice(o, o + size).arrayBuffer());
      return { v, meta: { type, start: 0, end: size, body: (h.getUint32(0) === 1 ? 16 : 8) } };
    }
    o += size;
  }
  return null;
}

export async function heicTiff(file: Blob): Promise<ArrayBuffer | null> {
  try {
    const found = await readMeta(file);
    if (!found) return null;
    const { v, meta } = found;
    const boxes = children(v, meta.body + 4, meta.end); // meta는 FullBox(버전·플래그 4바이트)
    const iinf = boxes.find((b) => b.type === "iinf");
    const iloc = boxes.find((b) => b.type === "iloc");
    if (!iinf || !iloc) return null;

    // iinf: Exif 항목 ID 찾기
    const iinfVer = v.getUint8(iinf.body);
    const entriesStart = iinf.body + 4 + (iinfVer === 0 ? 2 : 4);
    let exifId: number | null = null;
    for (const infe of children(v, entriesStart, iinf.end)) {
      if (infe.type !== "infe") continue;
      const ver = v.getUint8(infe.body);
      if (ver < 2) continue;
      const idSize = ver === 2 ? 2 : 4;
      const id = uint(v, infe.body + 4, idSize);
      if (fourcc(v, infe.body + 4 + idSize + 2) === "Exif") { exifId = id; break; }
    }
    if (exifId === null) return null;

    // iloc: 그 항목의 파일 위치 (base_offset + 첫 extent_offset)
    let o = iloc.body;
    const ver = v.getUint8(o); o += 4;
    const b1 = v.getUint8(o), b2 = v.getUint8(o + 1); o += 2;
    const offSize = b1 >> 4, lenSize = b1 & 15, baseSize = b2 >> 4, idxSize = ver === 1 || ver === 2 ? b2 & 15 : 0;
    const count = ver < 2 ? v.getUint16(o) : v.getUint32(o); o += ver < 2 ? 2 : 4;
    for (let i = 0; i < count; i++) {
      const id = ver < 2 ? v.getUint16(o) : v.getUint32(o); o += ver < 2 ? 2 : 4;
      let method = 0;
      if (ver === 1 || ver === 2) { method = v.getUint16(o) & 15; o += 2; }
      o += 2; // data_reference_index
      const base = uint(v, o, baseSize); o += baseSize;
      const extents = v.getUint16(o); o += 2;
      let first: [number, number] | null = null;
      for (let e = 0; e < extents; e++) {
        o += idxSize;
        const eo = uint(v, o, offSize); o += offSize;
        const el = uint(v, o, lenSize); o += lenSize;
        if (!first) first = [eo, el];
      }
      if (id !== exifId) continue;
      if (method !== 0 || !first) return null; // 파일 오프셋 방식만 지원
      const start = base + first[0];
      const length = first[1] || file.size - start;
      if (start + 4 > file.size || length < 12) return null;
      const payload = await file.slice(start, start + length).arrayBuffer();
      const skip = 4 + new DataView(payload).getUint32(0); // exif_tiff_header_offset
      return skip < payload.byteLength ? payload.slice(skip) : null;
    }
    return null;
  } catch {
    return null;
  }
}
