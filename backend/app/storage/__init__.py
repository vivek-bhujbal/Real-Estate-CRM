from functools import lru_cache

from app.core.config import get_settings
from app.storage.base import Storage, StoredFile
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage


@lru_cache
def get_storage() -> Storage:
    settings = get_settings()
    if settings.storage_backend == "s3":
        return S3Storage(settings)
    return LocalStorage(settings.storage_local_path)


__all__ = ["LocalStorage", "S3Storage", "Storage", "StoredFile", "get_storage"]
