"""저장소 어댑터. 개발: 비공개 로컬 폴더(STORAGE_BACKEND=local) / 운영: S3 호환 객체 저장소(STORAGE_BACKEND=object).
객체 저장소는 버킷을 비공개로 두고, 사진은 항상 권한을 확인하는 /media 경로를 통해서만 내려준다."""
import mimetypes
import os
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from app.core.config import settings

mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/heic", ".heic")


class Storage(Protocol):
    def save(self, key: str, data: bytes) -> None: ...
    def read(self, key: str) -> bytes: ...  # 없으면 FileNotFoundError
    def path_for(self, key: str) -> Path | None: ...  # 로컬 파일이면 경로 (FileResponse용), 아니면 None
    def delete(self, key: str) -> None: ...  # 없어도 오류 없음
    def list_keys(self, prefix: str) -> Iterator[tuple[str, float]]: ...  # (키, 마지막 수정 epoch초) — 정리 작업용
    def list_children(self, prefix: str) -> Iterator[str]: ...  # prefix 바로 아래 '폴더' 이름 — 사용자별로 나눠 정리하기 위함


def _check_key(key: str) -> None:
    if not key or key.startswith("/") or "\\" in key or any(part in ("", ".", "..") for part in key.split("/")):
        raise ValueError("invalid storage key")


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        _check_key(key)
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValueError("invalid storage key")
        return p

    def save(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent)  # 원자적 쓰기
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, p)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def path_for(self, key: str) -> Path | None:
        p = self._path(key)
        return p if p.is_file() else None

    def delete(self, key: str) -> None:
        p = self._path(key)
        p.unlink(missing_ok=True)
        # 빈 폴더 정리 (photos/<user>/<photo>/ 등)
        for parent in p.parents:
            if parent == self.root:
                break
            try:
                parent.rmdir()
            except OSError:
                break

    def list_keys(self, prefix: str) -> Iterator[tuple[str, float]]:
        base = self.root / prefix if prefix else self.root
        if not base.exists():
            return
        for path in base.rglob("*"):
            if path.is_file() and not path.name.startswith("tmp"):
                yield path.relative_to(self.root).as_posix(), path.stat().st_mtime

    def list_children(self, prefix: str) -> Iterator[str]:
        base = self.root / prefix if prefix else self.root
        if base.is_dir():
            for path in base.iterdir():
                if path.is_dir():
                    yield path.name


class S3Storage:
    """S3 호환 객체 저장소 (AWS S3, Cloudflare R2, MinIO, NCP Object Storage 등)."""

    def __init__(self, bucket: str, prefix: str = "", client=None):
        self.bucket = bucket
        self.prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""
        if client is None:
            import boto3
            from botocore.config import Config

            client = boto3.client(
                "s3",
                endpoint_url=settings.object_storage_endpoint_url or None,
                region_name=settings.object_storage_region or None,
                aws_access_key_id=settings.object_storage_access_key_id or None,
                aws_secret_access_key=settings.object_storage_secret_access_key or None,
                config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
            )
        self.client = client

    def _k(self, key: str) -> str:
        _check_key(key)
        return self.prefix + key

    def save(self, key: str, data: bytes) -> None:
        ctype = mimetypes.guess_type(key)[0] or "application/octet-stream"
        self.client.put_object(Bucket=self.bucket, Key=self._k(key), Body=data, ContentType=ctype)  # ACL 미지정 = 비공개

    def read(self, key: str) -> bytes:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self._k(key))
        except self.client.exceptions.NoSuchKey as e:
            raise FileNotFoundError(key) from e
        return obj["Body"].read()

    def path_for(self, key: str) -> Path | None:
        return None

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._k(key))

    def list_keys(self, prefix: str) -> Iterator[tuple[str, float]]:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix + prefix):
            for obj in page.get("Contents", []):
                yield obj["Key"][len(self.prefix):], obj["LastModified"].timestamp()

    def list_children(self, prefix: str) -> Iterator[str]:
        full = self.prefix + prefix
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=full, Delimiter="/"):
            for cp in page.get("CommonPrefixes", []):
                name = cp["Prefix"][len(full):].strip("/")
                if name:
                    yield name


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        if settings.storage_backend == "object":
            _storage = S3Storage(settings.object_storage_bucket, settings.object_storage_prefix)
        else:
            _storage = LocalStorage(settings.local_storage_path)
    return _storage


def set_storage(s: Storage) -> None:  # 테스트용
    global _storage
    _storage = s


def age_seconds(mtime: float) -> float:
    return time.time() - mtime
