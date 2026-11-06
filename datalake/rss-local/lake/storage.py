"""Almacenamiento de objetos con publicación atómica de objetos individuales."""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Protocol


class Store(Protocol):
    def read(self, key: str) -> bytes: ...
    def write(self, key: str, data: bytes) -> None: ...
    def exists(self, key: str) -> bool: ...
    def list(self, prefix: str) -> list[str]: ...
    def uri(self, key: str) -> str: ...


def checked_key(key: str) -> str:
    if not key or key.startswith("/") or ".." in PurePosixPath(key).parts:
        raise ValueError(f"Clave de objeto no válida: {key!r}")
    return key


class LocalStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        target = (self.root / checked_key(key)).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Clave fuera del directorio del lake")
        return target

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def write(self, key: str, data: bytes) -> None:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list(self, prefix: str) -> list[str]:
        if prefix:
            checked_key(prefix)
        return sorted(str(p.relative_to(self.root).as_posix())
                      for p in self.root.rglob("*")
                      if p.is_file() and not p.name.startswith(".pending-")
                      and p.relative_to(self.root).as_posix().startswith(prefix))

    def uri(self, key: str) -> str:
        return self._path(key).as_uri() + ("/" if key.endswith("/") else "")


class S3Store:
    def __init__(self, bucket: str, region: str):
        import boto3
        from botocore.config import Config
        self.bucket = bucket
        self.region = region
        self.client = boto3.client("s3", region_name=region, config=Config(
            retries={"mode": "standard", "total_max_attempts": 3},
            connect_timeout=10, read_timeout=60,
        ))

    def read(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=checked_key(key))
        except self.client.exceptions.NoSuchKey as exc:
            raise FileNotFoundError(key) from exc
        with response["Body"] as stream:
            return stream.read()

    def write(self, key: str, data: bytes) -> None:
        # Single PUT is atomic, including the small current manifest.
        self.client.put_object(Bucket=self.bucket, Key=checked_key(key), Body=data,
                               ServerSideEncryption="AES256")

    def exists(self, key: str) -> bool:
        # Prefix-scoped ListBucket does not grant GetObject missing-key disclosure.
        # Listing the exact prefix works with the restricted role; AccessDenied propagates.
        key = checked_key(key)
        response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=key, MaxKeys=1)
        return any(item["Key"] == key for item in response.get("Contents", []))

    def list(self, prefix: str) -> list[str]:
        if prefix:
            checked_key(prefix)
        pages = self.client.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket, Prefix=prefix)
        return sorted(obj["Key"] for page in pages for obj in page.get("Contents", []))

    def uri(self, key: str) -> str:
        return f"s3://{self.bucket}/{checked_key(key)}"


def read_json(store: Store, key: str):
    return json.loads(store.read(key))


def write_json(store: Store, key: str, value) -> None:
    store.write(key, json.dumps(value, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":"), allow_nan=False).encode("utf-8"))
