"""실제 포맷 검사·크기 제한·방향 보정·리사이즈. 표시용·썸네일·프로필 사진은 EXIF 없이 WebP로 재인코딩한다."""
import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError
from pi_heif import register_heif_opener

from app.core.config import settings
from app.core.errors import AppError

# HEIC/HEIF(아이폰 기본 형식) 읽기. pi-heif는 디코딩 전용이라 GPL 인코더(x265)를 포함하지 않는다.
# HEIF는 컨테이너의 회전 정보를 디코딩 때 적용하고 EXIF 방향을 1로 바꿔 주므로 이중 회전이 생기지 않는다.
register_heif_opener()

ALLOWED_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "HEIF": "heic"}
UNSUPPORTED_MSG = "JPEG, PNG, WebP, HEIC 이미지만 올릴 수 있습니다."
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
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError, RuntimeError) as e:
            raise AppError(415, "UNSUPPORTED_FORMAT", "이미지 파일을 읽을 수 없습니다.") from e

    return wrapper


@_guard
def process(data: bytes) -> ProcessedImage:
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
