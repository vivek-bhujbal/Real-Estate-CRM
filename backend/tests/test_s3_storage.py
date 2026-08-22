from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from app.core.config import Settings
from app.core.responses import private_file_response
from app.storage.s3 import S3Storage


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.last_options: dict[str, Any] = {}

    def put_object(self, **options: Any) -> None:
        self.last_options = options
        self.objects[(options["Bucket"], options["Key"])] = options["Body"]

    def upload_file(
        self, source: str, bucket: str, key: str, *, ExtraArgs: dict[str, str]
    ) -> None:
        self.last_options = ExtraArgs
        self.objects[(bucket, key)] = Path(source).read_bytes()

    def download_file(self, bucket: str, key: str, destination: str) -> None:
        Path(destination).write_bytes(self.objects[(bucket, key)])

    def delete_object(self, **options: Any) -> None:
        self.objects.pop((options["Bucket"], options["Key"]), None)


async def test_s3_storage_encrypts_objects_and_cleans_download_cache(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    client = FakeS3Client()
    monkeypatch.setattr("app.storage.s3.boto3.client", lambda *args, **kwargs: client)
    settings = Settings(
        jwt_secret_key="s3-test-signing-key-with-at-least-32-characters",
        storage_backend="s3",
        storage_temp_path=tmp_path,
        s3_bucket="private-bucket",
        s3_region="ap-south-1",
    )
    storage = S3Storage(settings)

    await storage.save_bytes(key="documents/org/document.private", content=b"private")
    assert client.last_options["ServerSideEncryption"] == "AES256"
    downloaded = await storage.path_for_read(key="documents/org/document.private")
    assert downloaded.temporary is True
    assert downloaded.path.read_bytes() == b"private"

    response = private_file_response(
        downloaded, filename="document.pdf", media_type="application/pdf"
    )
    assert response.background is not None
    await response.background()
    assert not downloaded.path.exists()


def test_kms_storage_requires_a_key_identifier() -> None:
    with pytest.raises(ValidationError):
        Settings(
            jwt_secret_key="kms-test-signing-key-with-at-least-32-characters",
            storage_backend="s3",
            s3_bucket="private-bucket",
            s3_region="ap-south-1",
            s3_server_side_encryption="aws:kms",
        )
