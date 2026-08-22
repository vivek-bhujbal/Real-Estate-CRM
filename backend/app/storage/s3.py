"""Private, encrypted S3-compatible object storage adapter."""

import asyncio
import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.core.config import Settings
from app.storage.base import StoredFile


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        if not settings.s3_bucket or not settings.s3_region:
            raise ValueError("S3 bucket and region must be configured")
        self.bucket = settings.s3_bucket
        self.temp_root = settings.storage_temp_path
        options: dict[str, Any] = {
            "region_name": settings.s3_region,
            "endpoint_url": settings.s3_endpoint_url,
        }
        if settings.s3_access_key_id:
            options["aws_access_key_id"] = settings.s3_access_key_id
            options["aws_secret_access_key"] = (
                settings.s3_secret_access_key.get_secret_value()
                if settings.s3_secret_access_key
                else None
            )
        self.client = boto3.client("s3", **options)
        self.encryption: dict[str, str] = {
            "ServerSideEncryption": settings.s3_server_side_encryption
        }
        if settings.s3_kms_key_id:
            self.encryption["SSEKMSKeyId"] = settings.s3_kms_key_id

    @staticmethod
    def _safe_key(key: str) -> str:
        parsed = PurePosixPath(key)
        if not key or key.startswith("/") or ".." in parsed.parts:
            raise ValueError("Invalid storage key")
        return str(parsed)

    async def save(self, *, key: str, source: Path) -> str:
        safe_key = self._safe_key(key)
        await asyncio.to_thread(
            self.client.upload_file,
            str(source),
            self.bucket,
            safe_key,
            ExtraArgs=self.encryption,
        )
        return key

    async def save_bytes(self, *, key: str, content: bytes) -> str:
        safe_key = self._safe_key(key)
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=safe_key,
            Body=content,
            **self.encryption,
        )
        return key

    async def delete(self, *, key: str) -> None:
        await asyncio.to_thread(
            self.client.delete_object, Bucket=self.bucket, Key=self._safe_key(key)
        )

    async def path_for_read(self, *, key: str) -> StoredFile:
        safe_key = self._safe_key(key)
        await asyncio.to_thread(self.temp_root.mkdir, parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            prefix="estateops-object-", suffix=".private", dir=self.temp_root, delete=False
        )
        path = Path(handle.name)
        handle.close()
        try:
            await asyncio.to_thread(
                self.client.download_file, self.bucket, safe_key, str(path)
            )
            await asyncio.to_thread(os.chmod, path, 0o600)
        except ClientError as exc:
            await asyncio.to_thread(path.unlink, missing_ok=True)
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                raise FileNotFoundError(key) from exc
            raise
        except Exception:
            await asyncio.to_thread(path.unlink, missing_ok=True)
            raise
        return StoredFile(path, temporary=True)
