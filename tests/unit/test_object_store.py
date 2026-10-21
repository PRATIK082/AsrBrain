"""Unit tests for the object store (ADR-0012).

The object store holds **bytes only** — no metadata, no provenance, no policy.
Those live in the relational registry. The store is content-addressed, so the
same bytes always land on the same key.
"""
import pytest

from src.objects import (LocalObjectStore, ObjectRef, S3ObjectStore,
                         content_hash, default_object_store)


def test_content_hash_is_the_sha256_of_the_bytes():
    data = b"autosar"
    assert content_hash(data) == content_hash(b"autosar")
    assert content_hash(data) != content_hash(b"autosar2")
    assert len(content_hash(data)) == 64


def test_local_store_round_trips_bytes(tmp_path):
    store = LocalObjectStore(root=str(tmp_path / "objects"))
    data = b"%PDF-1.7 fake spec bytes"
    ref = store.put(data)
    assert isinstance(ref, ObjectRef)
    assert ref.sha256 == content_hash(data)
    assert ref.size == len(data)
    assert store.exists(ref.key)
    assert store.get(ref.key) == data


def test_local_store_is_content_addressed(tmp_path):
    store = LocalObjectStore(root=str(tmp_path / "objects"))
    a = store.put(b"same bytes")
    b = store.put(b"same bytes")
    assert a.key == b.key
    assert a.uri == b.uri
    # The bytes are written once, under a sharded path.
    shard = tmp_path / "objects" / a.sha256[:2] / a.sha256
    assert shard.exists()


def test_local_store_delete_and_stat(tmp_path):
    store = LocalObjectStore(root=str(tmp_path / "objects"))
    ref = store.put(b"temporary")
    stat = store.stat(ref.key)
    assert stat["size"] == len(b"temporary")
    assert stat["sha256"] == ref.sha256
    store.delete(ref.key)
    assert not store.exists(ref.key)
    with pytest.raises(FileNotFoundError):
        store.get(ref.key)
    with pytest.raises(FileNotFoundError):
        store.stat(ref.key)


def test_local_store_presigned_url_points_at_the_object(tmp_path):
    store = LocalObjectStore(root=str(tmp_path / "objects"))
    ref = store.put(b"link me")
    url = store.presigned_url(ref.key)
    assert ref.sha256 in url
    assert url.startswith("file://")


def test_default_object_store_honours_the_backend_setting(tmp_path, monkeypatch):
    monkeypatch.setenv("OBJECT_STORE_BACKEND", "local")
    monkeypatch.setenv("OBJECT_STORE_ROOT", str(tmp_path / "objects"))
    store = default_object_store()
    assert isinstance(store, LocalObjectStore)

    monkeypatch.setenv("OBJECT_STORE_BACKEND", "s3")
    monkeypatch.setenv("OBJECT_STORE_BUCKET", "asrbrain")
    store = default_object_store()
    assert isinstance(store, S3ObjectStore)


def test_s3_store_reports_a_missing_client_clearly(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _no_boto3(name, *args, **kwargs):
        if name == "boto3":
            raise ImportError("no boto3")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_boto3)
    store = S3ObjectStore(bucket="asrbrain", endpoint_url="http://127.0.0.1:9000")
    with pytest.raises(RuntimeError) as exc:
        store.put(b"x")
    assert "boto3" in str(exc.value)


def test_s3_store_uris_are_bucket_scoped():
    store = S3ObjectStore(bucket="asrbrain", endpoint_url="http://127.0.0.1:9000")
    assert store._uri("abc") == "s3://asrbrain/abc"
    assert S3ObjectStore(bucket="b", prefix="objects")._uri("abc") == "s3://b/objects/abc"
