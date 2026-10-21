"""Object storage for raw source bytes (ADR-0012).

The object store holds **bytes only**. Every piece of metadata, provenance and
policy about an object lives in the relational registry
(`src/registry/`), so a lost bucket can never mean lost provenance.

Two implementations ship:

* `LocalObjectStore` — a content-addressed filesystem store. The default for
  development and for single-host installations.
* `S3ObjectStore` — speaks the S3 API. MinIO, Ceph RGW, SeaweedFS, Garage and
  hosted S3 all work; we never link MinIO's code (AGPL-3.0 stays at arm's
  length by design).

The dependency is on the **protocol**, not on a server. Swapping the backend
never changes the evidence model.
"""
from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = [
    "ObjectRef",
    "ObjectStore",
    "LocalObjectStore",
    "S3ObjectStore",
    "content_hash",
    "default_object_store",
]


def content_hash(data: bytes) -> str:
    """SHA-256 of the raw bytes, hex encoded. The identity of an object."""
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class ObjectRef:
    """Where an object lives and what it is."""

    key: str
    sha256: str
    size: int
    uri: str


@runtime_checkable
class ObjectStore(Protocol):
    """The narrow surface the product needs from an object store."""

    def put(self, data: bytes, key: str | None = None) -> ObjectRef:
        """Store bytes and return their reference."""

    def get(self, key: str) -> bytes:
        """Read the bytes back."""

    def exists(self, key: str) -> bool:
        """Is the object present?"""

    def stat(self, key: str) -> dict:
        """Metadata about the object (size, hash, modified time)."""

    def delete(self, key: str) -> bool:
        """Remove the object. Returns False when it was not there."""

    def presigned_url(self, key: str, expires_s: int = 3600) -> str:
        """A time-limited URL a browser can fetch."""


class LocalObjectStore:
    """Content-addressed filesystem store.

    Objects live at ``<root>/<sha[0:2]>/<sha>``. Re-storing identical bytes is
    a no-op, so the same content always yields the same key.
    """

    scheme = "local"

    def __init__(self, root: str = "data/objects"):
        self.root = Path(root)

    # -- helpers ---------------------------------------------------------- #

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / key

    def _uri(self, key: str) -> str:
        return f"{self.scheme}://{key}"

    # -- protocol --------------------------------------------------------- #

    def put(self, data: bytes, key: str | None = None) -> ObjectRef:
        digest = content_hash(data)
        obj_key = key or digest
        path = self._path(obj_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            # Write to a temporary file first so a crash cannot leave a
            # half-written object behind.
            tmp = path.with_suffix(".partial")
            tmp.write_bytes(data)
            os.replace(tmp, path)
        return ObjectRef(key=obj_key, sha256=digest, size=len(data), uri=self._uri(obj_key))

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise FileNotFoundError(f"object not found: {key}")
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def stat(self, key: str) -> dict:
        path = self._path(key)
        if not path.exists():
            raise FileNotFoundError(f"object not found: {key}")
        data = path.read_bytes()
        return {
            "key": key,
            "uri": self._uri(key),
            "size": len(data),
            "sha256": content_hash(data),
            "modified_at": path.stat().st_mtime,
        }

    def delete(self, key: str) -> bool:
        path = self._path(key)
        if not path.exists():
            return False
        path.unlink()
        return True

    def presigned_url(self, key: str, expires_s: int = 3600) -> str:
        # There is no server to sign for; a local file URL is the honest answer.
        return self._path(key).resolve().as_uri()

    # -- maintenance ------------------------------------------------------ #

    def clear(self) -> None:
        """Remove every object (development helper)."""
        if self.root.exists():
            shutil.rmtree(self.root)


class S3ObjectStore:
    """S3-API object store.

    The client library is imported lazily so the product installs and runs
    without it; only the S3 deployment needs it.
    """

    scheme = "s3"

    def __init__(self, bucket: str, endpoint_url: str = "", region: str = "",
                 access_key: str = "", secret_key: str = "", prefix: str = ""):
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.region = region
        self.prefix = prefix.strip("/")
        self._access_key = access_key
        self._secret_key = secret_key
        self._client = None

    # -- client ----------------------------------------------------------- #

    def _connect(self):
        if self._client is not None:
            return self._client
        try:
            import boto3  # type: ignore
        except ImportError as e:  # pragma: no cover - depends on deployment
            raise RuntimeError(
                "the S3 object store needs the 'boto3' client library; install it or "
                "set OBJECT_STORE_BACKEND=local"
            ) from e
        kwargs: dict = {}
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        if self.region:
            kwargs["region_name"] = self.region
        if self._access_key:
            kwargs["aws_access_key_id"] = self._access_key
        if self._secret_key:
            kwargs["aws_secret_access_key"] = self._secret_key
        self._client = boto3.client("s3", **kwargs)
        return self._client

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def _uri(self, key: str) -> str:
        return f"{self.scheme}://{self.bucket}/{self._key(key)}"

    # -- protocol --------------------------------------------------------- #

    def put(self, data: bytes, key: str | None = None) -> ObjectRef:
        digest = content_hash(data)
        obj_key = key or digest
        self._connect().put_object(Bucket=self.bucket, Key=self._key(obj_key), Body=data)
        return ObjectRef(key=obj_key, sha256=digest, size=len(data), uri=self._uri(obj_key))

    def get(self, key: str) -> bytes:
        obj = self._connect().get_object(Bucket=self.bucket, Key=self._key(key))
        return obj["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self._connect().head_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except Exception:
            return False

    def stat(self, key: str) -> dict:
        head = self._connect().head_object(Bucket=self.bucket, Key=self._key(key))
        return {
            "key": key,
            "uri": self._uri(key),
            "size": int(head.get("ContentLength") or 0),
            "sha256": (head.get("Metadata") or {}).get("sha256", ""),
            "modified_at": (head.get("LastModified") or 0),
        }

    def delete(self, key: str) -> bool:
        if not self.exists(key):
            return False
        self._connect().delete_object(Bucket=self.bucket, Key=self._key(key))
        return True

    def presigned_url(self, key: str, expires_s: int = 3600) -> str:
        return self._connect().generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": self._key(key)},
            ExpiresIn=expires_s,
        )


def default_object_store() -> ObjectStore:
    """Build the configured object store.

    `OBJECT_STORE_BACKEND=local` (default) or `s3`.
    """
    backend = os.environ.get("OBJECT_STORE_BACKEND", "local").strip().lower()
    if backend == "s3":
        bucket = os.environ.get("OBJECT_STORE_BUCKET", "")
        if not bucket:
            raise RuntimeError("OBJECT_STORE_BUCKET is required for the s3 object store")
        return S3ObjectStore(
            bucket=bucket,
            endpoint_url=os.environ.get("OBJECT_STORE_ENDPOINT_URL", ""),
            region=os.environ.get("OBJECT_STORE_REGION", ""),
            access_key=os.environ.get("OBJECT_STORE_ACCESS_KEY", ""),
            secret_key=os.environ.get("OBJECT_STORE_SECRET_KEY", ""),
            prefix=os.environ.get("OBJECT_STORE_PREFIX", ""),
        )
    return LocalObjectStore(os.environ.get("OBJECT_STORE_ROOT", "data/objects"))
