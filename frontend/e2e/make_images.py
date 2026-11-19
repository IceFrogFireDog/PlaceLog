"""E2E용 테스트 사진 만들기 (백엔드 가상환경의 Pillow 사용). 사용: python make_images.py <폴더> <백엔드 폴더>"""
import shutil
import sys
from pathlib import Path

from PIL import ExifTags, Image

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)


def jpeg(path, size, color, gps=None, dt=None, offset=None):
    img = Image.new("RGB", size, color)
    exif = Image.Exif()
    exif[0x010F] = "E2ECam"
    exif[0x0110] = "Model 7"
    ifd = exif.get_ifd(ExifTags.IFD.Exif)
    if dt:
        ifd[0x9003] = dt
    if offset:
        ifd[0x9011] = offset
    if gps:
        def dms(v):
            v = abs(v); d = int(v); m = int((v - d) * 60); s = round(((v - d) * 60 - m) * 60, 4)
            return (float(d), float(m), float(s))
        g = exif.get_ifd(ExifTags.IFD.GPSInfo)
        g[1] = "N" if gps[0] >= 0 else "S"; g[2] = dms(gps[0])
        g[3] = "E" if gps[1] >= 0 else "W"; g[4] = dms(gps[1])
    img.save(path, format="JPEG", exif=exif, quality=90)


jpeg(out / "gyeongbok.jpg", (800, 600), (180, 90, 40), gps=(37.57961, 126.97702), dt="2025:10:03 14:05:00", offset="+09:00")
jpeg(out / "tokyo.jpg", (640, 480), (40, 90, 180), gps=(35.65858, 139.74543), dt="2025:12:24 19:30:00")  # 시간대 없음
jpeg(out / "avatar.jpg", (500, 300), (20, 160, 90), gps=(37.5, 127.0))
Image.new("RGB", (600, 400), (120, 120, 200)).save(out / "nogps.png")
whole = (out / "gyeongbok.jpg").read_bytes()
(out / "broken.jpg").write_bytes(whole[: len(whole) // 2])  # 헤더는 멀쩡하고 이미지 데이터가 잘린 파일 → 변환 실패
fixtures = Path(sys.argv[2]).resolve() / "tests/fixtures"  # HEIC·RAW 시험 파일은 백엔드 테스트 것을 그대로 쓴다
shutil.copy(fixtures / "iphone_gps.heic", out / "IMG_0001.HEIC")
shutil.copy(fixtures / "raw_gps.dng", out / "DSC_0001.DNG")  # 카메라 RAW (세로, GPS·촬영일 포함)
