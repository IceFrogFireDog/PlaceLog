"""실제 포맷 검사·크기 제한·방향 보정·리사이즈. 표시용·썸네일·프로필 사진은 EXIF 없이 WebP로 재인코딩한다."""
import io
from dataclasses import dataclass

import rawpy
from PIL import Image, ImageOps, UnidentifiedImageError
from pi_heif import register_heif_opener

from app.core.config import settings
from app.core.errors import AppError

# HEIC/HEIF(아이폰 기본 형식) 읽기. pi-heif는 디코딩 전용이라 GPL 인코더(x265)를 포함하지 않는다.
# HEIF는 컨테이너의 회전 정보를 디코딩 때 적용하고 EXIF 방향을 1로 바꿔 주므로 이중 회전이 생기지 않는다.
register_heif_opener()

ALLOWED_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "HEIF": "heic"}
UNSUPPORTED_MSG = "JPEG, PNG, WebP, HEIC 이미지와 카메라 RAW(DNG·CR2·CR3·NEF·ARW 등)만 올릴 수 있습니다."
# 카메라 RAW는 LibRaw(rawpy)로 읽는다. 원본 확장자는 올린 파일 이름을 따르고, 모르는 이름이면 "raw".
RAW_EXTS = {"dng", "cr2", "cr3", "crw", "nef", "nrw", "arw", "srf", "sr2", "srw", "orf", "rw2", "rwl", "raf", "pef", "3fr", "iiq", "erf", "mos", "kdc", "dcr", "x3f"}
RAW_MIN_PREVIEW_EDGE = 1600  # 카메라가 넣어 둔 JPEG 미리보기가 이보다 크면 그것을 쓴다 (현상보다 훨씬 빠름)
_ROTATED = {5, 6, 7, 8}  # EXIF 방향 중 가로·세로가 바뀌는 값

# 동시 처리 수 제한은 photo_service의 anyio CapacityLimiter(IMAGE_WORKERS)가 맡는다.
# (스레드 안에서 세마포어로 기다리면 공용 스레드풀을 점유해 다른 API가 멈춘다)

# Pillow 자체 폭탄 검사(2배 초과 시 오류)는 마지막 방어선. 1차 검사는 아래에서 직접 한다.
Image.MAX_IMAGE_PIXELS = settings.max_image_pixels


@dataclass
class ProcessedImage:
    original_ext: str
    width: int
    height: int
    display: bytes
    thumbnail: bytes


def _encode(img: Image.Image, long_edge: int) -> bytes:
    copy = img.copy()
    copy.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)  # 작은 사진은 확대하지 않음
    buf = io.BytesIO()
    copy.save(buf, format="WEBP", quality=85, method=4)  # exif 인자 없음 → EXIF 제거
    return buf.getvalue()


def _transpose(img: Image.Image) -> Image.Image:
    try:
        return ImageOps.exif_transpose(img)
    except Exception:  # noqa: BLE001 - 손상된 방향 태그는 무시
        return img


def _probe(data: bytes) -> tuple[str, int, int, int | None]:
    with Image.open(io.BytesIO(data)) as probe:
        fmt = probe.format or ""
        w, h = probe.size
        try:
            orientation = probe.getexif().get(0x0112)
        except Exception:  # noqa: BLE001
            orientation = None
    if fmt not in ALLOWED_FORMATS:
        raise AppError(415, "UNSUPPORTED_FORMAT", UNSUPPORTED_MSG)
    if w * h > settings.max_image_pixels:
        raise AppError(413, "IMAGE_TOO_LARGE", "이미지 해상도가 너무 큽니다.")
    return fmt, w, h, orientation


def _decode(data: bytes, fmt: str, raw_w: int, raw_h: int, edge: int) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    if fmt == "JPEG":
        # JPEG는 필요한 크기 이상으로만 축소 디코딩해 메모리를 크게 줄인다.
        # draft는 가로·세로 모두 요청 크기 이상을 유지하므로 비율을 맞춘 크기를 요청한다.
        req = (edge, max(1, edge * raw_h // raw_w)) if raw_w >= raw_h else (max(1, edge * raw_w // raw_h), edge)
        img.draft("RGB", req)
    img.load()
    img = _transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() or img.mode == "P" else "RGB")
    return img


def _guard(fn):
    def wrapper(data: bytes, *a, **kw):
        try:
            return fn(data, *a, **kw)
        except AppError:
            raise
        except Image.DecompressionBombError as e:
            raise AppError(413, "IMAGE_TOO_LARGE", "이미지 해상도가 너무 큽니다.") from e
        except rawpy.LibRawTooBigError as e:
            raise AppError(413, "IMAGE_TOO_LARGE", "이미지 해상도가 너무 큽니다.") from e
        except (rawpy.LibRawError, UnidentifiedImageError, OSError, SyntaxError, ValueError, RuntimeError) as e:
            raise AppError(415, "UNSUPPORTED_FORMAT", "이미지 파일을 읽을 수 없습니다.") from e

    return wrapper


# ---------- 카메라 RAW ----------

def _raw_ext(filename: str | None) -> str:
    ext = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    return ext if ext in RAW_EXTS else "raw"


def _pillow_format(data: bytes) -> str | None:
    """Pillow가 아는 일반 이미지 형식이면 그 이름, 아니면 None (RAW 후보)."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            return im.format if im.format in ALLOWED_FORMATS else None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        return None


def _raw_probe(data: bytes) -> tuple[int, int]:
    """LibRaw로 헤더만 읽어 방향 보정 후 크기를 구한다 (픽셀 현상 없음)."""
    if not settings.max_raw_upload_bytes:
        raise AppError(415, "UNSUPPORTED_FORMAT", "JPEG, PNG, WebP, HEIC 이미지만 올릴 수 있습니다.")
    try:
        with rawpy.imread(io.BytesIO(data)) as raw:
            w, h, flip = raw.sizes.width, raw.sizes.height, raw.sizes.flip
    except rawpy.LibRawError as e:
        raise AppError(415, "UNSUPPORTED_FORMAT", UNSUPPORTED_MSG) from e
    if w <= 0 or h <= 0:
        raise AppError(415, "UNSUPPORTED_FORMAT", UNSUPPORTED_MSG)
    if w * h > settings.max_image_pixels:
        raise AppError(413, "IMAGE_TOO_LARGE", "이미지 해상도가 너무 큽니다.")
    return (h, w) if flip in (5, 6) else (w, h)


_FLIP = {3: Image.Transpose.ROTATE_180, 5: Image.Transpose.ROTATE_90, 6: Image.Transpose.ROTATE_270}  # LibRaw flip → 회전


def _raw_image(data: bytes) -> Image.Image:
    """RAW → RGB. 충분히 큰 내장 JPEG 미리보기가 있으면 그것을, 없으면 절반 크기로 현상한다."""
    with rawpy.imread(io.BytesIO(data)) as raw:
        flip = raw.sizes.flip
        try:
            thumb = raw.extract_thumb()
        except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
            thumb = None
        if thumb is not None:
            if thumb.format == rawpy.ThumbFormat.JPEG:
                img = Image.open(io.BytesIO(thumb.data))
                big = max(img.size) >= RAW_MIN_PREVIEW_EDGE
                if big:
                    img.draft("RGB", (settings.display_long_edge, settings.display_long_edge))
            else:  # 비트맵 미리보기 (numpy 배열)
                img = Image.fromarray(thumb.data)
                big = max(img.size) >= RAW_MIN_PREVIEW_EDGE
            if big:
                img.load()
                img = img.convert("RGB")
                # 미리보기의 자체 EXIF 방향은 믿지 않고 RAW의 방향 값만 적용 (이중 회전 방지)
                return img.transpose(_FLIP[flip]) if flip in _FLIP else img
        # 미리보기가 없거나 작으면 현상 (LibRaw가 방향까지 적용). half_size로 메모리·시간을 1/4로
        rgb = raw.postprocess(use_camera_wb=True, half_size=True, output_bps=8)
        return Image.fromarray(rgb).convert("RGB")


@dataclass
class Probe:
    original_ext: str
    width: int  # 방향 보정 후 크기
    height: int
    raw: bool = False


@_guard
def probe(data: bytes, filename: str | None = None) -> Probe:
    """업로드할 때 하는 빠른 검사: 실제 형식·해상도 한도·방향 보정 후 크기 (픽셀 디코딩 없이 헤더만 읽음)."""
    if _pillow_format(data) is None:
        w, h = _raw_probe(data)
        return Probe(original_ext=_raw_ext(filename), width=w, height=h, raw=True)
    fmt, w, h, orientation = _probe(data)
    if orientation in _ROTATED:
        w, h = h, w
    return Probe(original_ext=ALLOWED_FORMATS[fmt], width=w, height=h)


@_guard
def process(data: bytes) -> ProcessedImage:
    if _pillow_format(data) is None:  # 카메라 RAW
        _raw_probe(data)
        with _raw_image(data) as img:
            return ProcessedImage(
                original_ext="raw", width=img.width, height=img.height,
                display=_encode(img, settings.display_long_edge), thumbnail=_encode(img, settings.thumbnail_long_edge),
            )
    fmt, w, h, orientation = _probe(data)
    raw_w, raw_h = w, h
    if orientation in _ROTATED:
        w, h = h, w
    with _decode(data, fmt, raw_w, raw_h, settings.display_long_edge) as img:
        return ProcessedImage(
            original_ext=ALLOWED_FORMATS[fmt],
            width=w,
            height=h,
            display=_encode(img, settings.display_long_edge),
            thumbnail=_encode(img, settings.thumbnail_long_edge),
        )


@_guard
def make_avatar(data: bytes) -> bytes:
    """가운데를 정사각형으로 잘라 AVATAR_SIZE px WebP로 만든다 (EXIF 제거)."""
    fmt, w, h, _ = _probe(data)
    size = settings.avatar_size
    with _decode(data, fmt, w, h, size * 2) as img:
        square = ImageOps.fit(img, (size, size), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        buf = io.BytesIO()
        square.save(buf, format="WEBP", quality=85, method=4)
        return buf.getvalue()
