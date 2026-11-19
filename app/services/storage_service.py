"""저장소 어댑터. 사진 파일은 비공개 로컬 폴더(LOCAL_STORAGE_PATH)에 두고, 항상 권한을 확인하는 /media 경로로만 내려준다."""
import os
import tempfile
from pathlib import Path
from typing import Protocol

from app.core.config import settings


class Storage(Protocol):
    def save(self, key: str, data: bytes) -> None: ...
    def read(self, key: str) -> bytes: ...  # 없으면 FileNotFoundError
    def path_for(self, key: str) -> Path | None: ...  # 로컬 파일이면 경로 (FileResponse용), 아니면 None
    def delete(self, key: str) -> None: ...  # 없어도 오류 없음


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


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = LocalStorage(settings.local_storage_path)
    return _storage


def set_storage(s: Storage) -> None:  # 테스트용
    global _storage
    _storage = s
