"""Exercises the R2 adapter's real boto3 code path against a simulated S3 (moto).

This validates request construction and error mapping; it does not contact Cloudflare.
"""
import boto3
import pytest
from moto import mock_aws

from app.storage import get_object_storage
from app.storage.base import StorageError
from app.storage.r2 import R2Storage

BUCKET = "dailymail-test"
# moto only intercepts AWS hostnames; the adapter code path is identical for any endpoint_url.
ENDPOINT = "https://s3.us-east-1.amazonaws.com"


@pytest.fixture
def r2():
    with mock_aws():
        boto3.client(
            "s3",
            endpoint_url=ENDPOINT,
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name="auto",
        ).create_bucket(Bucket=BUCKET)
        yield R2Storage(
            endpoint_url=ENDPOINT,
            bucket=BUCKET,
            access_key_id="test",
            secret_access_key="test",
        )


def test_put_get_delete_round_trip(r2):
    r2.put("abc123.pdf", b"%PDF-1.4 body", "application/pdf")
    assert r2.get("abc123.pdf") == b"%PDF-1.4 body"
    r2.delete("abc123.pdf")
    with pytest.raises(StorageError):
        r2.get("abc123.pdf")


def test_stored_object_carries_content_type(r2):
    r2.put("img.png", b"\x89PNG", "image/png")
    client = boto3.client(
        "s3", endpoint_url=ENDPOINT, aws_access_key_id="test", aws_secret_access_key="test", region_name="auto"
    )
    head = client.head_object(Bucket=BUCKET, Key="img.png")
    assert head["ContentType"] == "image/png"


def test_missing_object_maps_to_storage_error(r2):
    with pytest.raises(StorageError):
        r2.get("does-not-exist")


def test_factory_refuses_to_start_without_credentials(monkeypatch):
    from app.storage import StorageNotConfiguredError

    settings = type("S", (), {
        "r2_endpoint_url": "",
        "r2_account_id": "",
        "r2_access_key_id": "",
        "r2_secret_access_key": "",
        "r2_bucket_name": "b",
    })()
    monkeypatch.setattr("app.storage.get_settings", lambda: settings)
    get_object_storage.cache_clear()
    try:
        with pytest.raises(StorageNotConfiguredError):
            get_object_storage()
    finally:
        get_object_storage.cache_clear()
