"""EXIF 추출. 누락·손상은 예외 없이 None으로 처리한다. 원본 GPS 값은 로그에 남기지 않는다."""
import io
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from PIL import ExifTags, Image

from app.core.database import taken_at_in_range


@dataclass
class ExifInfo:
    latitude: float | None = None
    longitude: float | None = None
    taken_at: datetime | None = None  # 시간대가 있을 때만 UTC aware
    taken_local: str | None = None  # 시간대 없는 원문(사용자 확인용)
    taken_timezone: str | None = None  # "+09:00"
    camera: str | None = None
    lens: str | None = None
    focal_length: float | None = None
    aperture: float | None = None
    shutter_speed: str | None = None
    iso: int | None = None


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _dms(v, ref) -> float | None:
    try:
        d, m, s = (float(x) for x in v)
        val = d + m / 60 + s / 3600
        if str(ref).upper() in ("S", "W"):
            val = -val
        return val
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _clean(s) -> str | None:
    if s is None:
        return None
    if isinstance(s, bytes):
        s = s.decode(errors="ignore")
    s = str(s).replace("\x00", "").strip()
    return s[:120] or None


def _parse_offset(off: str) -> timezone | None:
    try:
        sign = -1 if off.startswith("-") else 1
        h, m = off.lstrip("+-").split(":")
        return timezone(sign * timedelta(hours=int(h), minutes=int(m)))
    except (ValueError, AttributeError):
        return None


def _load(data: bytes) -> Image.Exif | None:
    try:
        with Image.open(io.BytesIO(data)) as img:
            exif = img.getexif()
            return exif if exif else None
    except Exception:  # noqa: BLE001 - 손상 EXIF 허용
        return None


def extract(data: bytes) -> ExifInfo:
    info = ExifInfo()
    exif = _load(data)
    if exif is None:
        return info
    try:
        ifd = exif.get_ifd(ExifTags.IFD.Exif)
        gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    except Exception:  # noqa: BLE001
        return info

    try:
        if gps:
            lat, lon = _dms(gps.get(2), gps.get(1)), _dms(gps.get(4), gps.get(3))
            if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0):
                info.latitude, info.longitude = round(lat, 7), round(lon, 7)
    except Exception:  # noqa: BLE001
        pass

    try:
        raw = ifd.get(0x9003) or exif.get(0x0132)  # DateTimeOriginal / DateTime
        if raw:
            local = datetime.strptime(_clean(raw) or "", "%Y:%m:%d %H:%M:%S")
            info.taken_local = local.isoformat()
            off = _clean(ifd.get(0x9011))  # OffsetTimeOriginal
            tz = _parse_offset(off) if off else None
            if tz is not None:
                info.taken_timezone = off
                at = local.replace(tzinfo=tz).astimezone(timezone.utc)
                if taken_at_in_range(at):
                    info.taken_at = at
                else:
                    info.taken_timezone = None
    except Exception:  # noqa: BLE001
        pass

    try:
        make, model = _clean(exif.get(0x010F)), _clean(exif.get(0x0110))
        if model and make and not model.lower().startswith(make.lower()):
            info.camera = f"{make} {model}"[:120]
        else:
            info.camera = model or make
        info.lens = _clean(ifd.get(0xA434))
        info.focal_length = _f(ifd.get(0x920A))
        info.aperture = _f(ifd.get(0x829D))
        exp = _f(ifd.get(0x829A))
        if exp:
            info.shutter_speed = f"1/{round(1 / exp)}" if exp < 1 else f"{exp:g}"
        iso = ifd.get(0x8827)
        if isinstance(iso, (tuple, list)):
            iso = iso[0] if iso else None
        info.iso = int(iso) if iso is not None else None
    except Exception:  # noqa: BLE001
        pass
    return info
