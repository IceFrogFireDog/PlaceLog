"""테스트용 DNG(RAW) 파일 만들기. 실제 카메라 RAW 대신 LibRaw가 읽을 수 있는 최소 DNG를 직접 쓴다.

  python tests/fixtures/make_raw.py      → tests/fixtures/raw_gps.dng, raw_preview.dng

- raw_gps.dng: 600x400 RGGB 센서 데이터, 방향 6(90° 회전), EXIF 촬영일(+09:00)·GPS(37.5445, 127.0374)
- raw_preview.dng: 1800x1200 JPEG 미리보기(초록색) + 하위 IFD의 센서 데이터 → 미리보기 경로 확인용
"""
import io
import struct
from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent
BYTE, ASCII, SHORT, LONG, RATIONAL, UNDEFINED, SRATIONAL = 1, 2, 3, 4, 5, 7, 10
SIZES = {BYTE: 1, ASCII: 1, SHORT: 2, LONG: 4, RATIONAL: 8, UNDEFINED: 1, SRATIONAL: 8}


class Tiff:
    """리틀엔디언 TIFF 작성기: 데이터를 먼저 쓰고, 자식 IFD → 부모 IFD 순서로 덧붙인다."""

    def __init__(self):
        self.buf = bytearray(b"II*\x00\x00\x00\x00\x00")

    def blob(self, data: bytes) -> int:
        if len(self.buf) % 2:
            self.buf += b"\x00"
        off = len(self.buf)
        self.buf += data
        return off

    @staticmethod
    def _pack(typ, values) -> bytes:
        if typ == ASCII:
            return values.encode() + b"\x00"
        if typ in (BYTE, UNDEFINED):
            return bytes(values)
        if typ == SHORT:
            return struct.pack(f"<{len(values)}H", *values)
        if typ == LONG:
            return struct.pack(f"<{len(values)}I", *values)
        if typ == RATIONAL:
            return b"".join(struct.pack("<II", n, d) for n, d in values)
        if typ == SRATIONAL:
            return b"".join(struct.pack("<ii", n, d) for n, d in values)
        raise ValueError(typ)

    def ifd(self, entries: dict[int, tuple[int, object]]) -> int:
        packed = []
        for tag in sorted(entries):
            typ, values = entries[tag]
            data = self._pack(typ, values)
            count = len(data) // SIZES[typ]
            if len(data) <= 4:
                packed.append(struct.pack("<HHI", tag, typ, count) + data.ljust(4, b"\x00"))
            else:
                packed.append(struct.pack("<HHII", tag, typ, count, self.blob(data)))
        body = struct.pack("<H", len(packed)) + b"".join(packed) + struct.pack("<I", 0)
        return self.blob(body)

    def finish(self, ifd0: int) -> bytes:
        self.buf[4:8] = struct.pack("<I", ifd0)
        return bytes(self.buf)


def _dms(v: float):
    v = abs(v)
    d = int(v)
    m = int((v - d) * 60)
    s = round(((v - d) * 60 - m) * 60 * 1000)
    return [(d, 1), (m, 1), (s, 1000)]


def _cfa(w: int, h: int) -> bytes:
    """RGGB 패턴. 위쪽은 붉고 아래쪽은 푸른 그라데이션 (12비트 값을 16비트에 저장)."""
    rows = []
    for y in range(h):
        t = y / max(1, h - 1)
        r, g, b = int(3200 * (1 - t) + 300), 1200, int(3200 * t + 300)
        even = struct.pack("<HH", r, g) * (w // 2)
        odd = struct.pack("<HH", g, b) * (w // 2)
        rows.append(even if y % 2 == 0 else odd)
    return b"".join(rows)


def _raw_entries(t: Tiff, w: int, h: int, subfile: int) -> dict:
    data = _cfa(w, h)
    return {
        254: (LONG, [subfile]),           # NewSubfileType (0 = 주 이미지)
        256: (LONG, [w]), 257: (LONG, [h]),
        258: (SHORT, [16]),               # BitsPerSample
        259: (SHORT, [1]),                # 압축 없음
        262: (SHORT, [32803]),            # CFA
        273: (LONG, [t.blob(data)]),      # StripOffsets
        277: (SHORT, [1]),
        278: (LONG, [h]),
        279: (LONG, [len(data)]),
        284: (SHORT, [1]),
        33421: (SHORT, [2, 2]),           # CFARepeatPatternDim
        33422: (BYTE, [0, 1, 1, 2]),      # CFAPattern RGGB
        50714: (LONG, [0]),               # BlackLevel
        50717: (LONG, [4095]),            # WhiteLevel
    }


def _camera_entries(t: Tiff, orientation: int, exif_ifd: int | None, gps_ifd: int | None) -> dict:
    e = {
        271: (ASCII, "PhotoGlobe"), 272: (ASCII, "Test DNG"),
        274: (SHORT, [orientation]),
        50706: (BYTE, [1, 4, 0, 0]),      # DNGVersion
        50707: (BYTE, [1, 1, 0, 0]),
        50708: (ASCII, "PhotoGlobe Test DNG"),
        50721: (SRATIONAL, [(1, 1), (0, 1), (0, 1), (0, 1), (1, 1), (0, 1), (0, 1), (0, 1), (1, 1)]),  # ColorMatrix1
        50728: (RATIONAL, [(1, 1), (1, 1), (1, 1)]),  # AsShotNeutral
        50778: (SHORT, [21]),             # CalibrationIlluminant1 = D65
    }
    if exif_ifd is not None:
        e[34665] = (LONG, [exif_ifd])
    if gps_ifd is not None:
        e[34853] = (LONG, [gps_ifd])
    return e


def raw_gps() -> bytes:
    t = Tiff()
    exif = t.ifd({36867: (ASCII, "2025:08:15 09:30:00"), 36881: (ASCII, "+09:00")})
    gps = t.ifd({
        0: (BYTE, [2, 3, 0, 0]),
        1: (ASCII, "N"), 2: (RATIONAL, _dms(37.5445)),
        3: (ASCII, "E"), 4: (RATIONAL, _dms(127.0374)),
    })
    entries = _raw_entries(t, 600, 400, 0) | _camera_entries(t, 6, exif, gps)
    return t.finish(t.ifd(entries))


def raw_preview() -> bytes:
    t = Tiff()
    jpg = io.BytesIO()
    Image.new("RGB", (1800, 1200), (30, 200, 60)).save(jpg, "JPEG", quality=80)
    raw_ifd = t.ifd(_raw_entries(t, 600, 400, 0))
    preview = t.blob(jpg.getvalue())
    ifd0 = {
        254: (LONG, [1]),                 # 미리보기
        256: (LONG, [1800]), 257: (LONG, [1200]),
        258: (SHORT, [8, 8, 8]),
        259: (SHORT, [7]),                # JPEG
        262: (SHORT, [6]),                # YCbCr
        273: (LONG, [preview]), 277: (SHORT, [3]), 278: (LONG, [1200]), 279: (LONG, [len(jpg.getvalue())]),
        330: (LONG, [raw_ifd]),           # SubIFDs → 센서 데이터
    } | _camera_entries(t, 1, None, None)
    return t.finish(t.ifd(ifd0))


if __name__ == "__main__":
    (HERE / "raw_gps.dng").write_bytes(raw_gps())
    (HERE / "raw_preview.dng").write_bytes(raw_preview())
    print("written", [p.name for p in HERE.glob("*.dng")])
