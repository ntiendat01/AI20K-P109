"""Document object storage with filesystem and S3 implementations."""

from __future__ import annotations

import os
import tempfile
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path


class ObjectStorage(ABC):
    @abstractmethod
    def put(self, key: str, content: bytes, content_type: str) -> str: ...

    @abstractmethod
    def get(self, reference: str) -> bytes: ...

    @abstractmethod
    def exists(self, reference: str) -> bool: ...

    @abstractmethod
    def delete(self, reference: str) -> None: ...

    @contextmanager
    def materialize(self, reference: str, filename: str):
        """Provide a temporary local path for PDF/OCR libraries."""
        suffix = Path(filename).suffix
        descriptor, temporary_name = tempfile.mkstemp(suffix=suffix)
        try:
            with os.fdopen(descriptor, "wb") as temporary_file:
                temporary_file.write(self.get(reference))
            yield Path(temporary_name)
        finally:
            Path(temporary_name).unlink(missing_ok=True)


class FilesystemObjectStorage(ObjectStorage):
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, reference: str) -> Path:
        path = Path(reference)
        if path.is_absolute() or path.parts[: len(self.root.parts)] == self.root.parts:
            return path
        return self.root / path

    def put(self, key: str, content: bytes, content_type: str) -> str:
        del content_type
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return str(path)

    def get(self, reference: str) -> bytes:
        return self._path(reference).read_bytes()

    def exists(self, reference: str) -> bool:
        return self._path(reference).is_file()

    def delete(self, reference: str) -> None:
        self._path(reference).unlink(missing_ok=True)

    @contextmanager
    def materialize(self, reference: str, filename: str):
        del filename
        yield self._path(reference)


class S3ObjectStorage(ObjectStorage):
    def __init__(self, bucket: str, region: str, prefix: str = "uploads") -> None:
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = boto3.client(
            "s3",
            region_name=region,
            config=Config(retries={"mode": "standard", "total_max_attempts": 3}, connect_timeout=5, read_timeout=30),
        )

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key.lstrip('/')}" if self.prefix else key.lstrip("/")

    def put(self, key: str, content: bytes, content_type: str) -> str:
        object_key = self._key(key)
        self.client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=content,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        return object_key

    def get(self, reference: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=reference)
        with response["Body"] as body:
            return body.read()

    def exists(self, reference: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=reference)
            return True
        except Exception as error:
            from botocore.exceptions import ClientError

            if not isinstance(error, ClientError):
                raise
            if error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return False
            raise

    def delete(self, reference: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=reference)
