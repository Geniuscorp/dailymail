"""Cloudflare R2 adapter using its S3-compatible API."""
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.storage.base import StorageError


class R2Storage:
    def __init__(self, *, endpoint_url: str, bucket: str, access_key_id: str, secret_access_key: str):
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Failed to store object") from exc

    def get(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return response["Body"].read()
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Failed to read object") from exc

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Failed to delete object") from exc
