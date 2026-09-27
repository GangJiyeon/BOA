from functools import lru_cache

import boto3
from botocore.config import Config

from app.core.config import get_settings

URL_EXPIRES_SECONDS = 300


@lru_cache
def _client():
    s = get_settings()
    # 키가 비어 있으면 None을 넘겨 boto3 기본 자격증명(EC2 IAM Role 등)을 쓰게 한다
    return boto3.client(
        "s3",
        region_name=s.aws_region,
        aws_access_key_id=s.aws_access_key_id or None,
        aws_secret_access_key=s.aws_secret_access_key or None,
        config=Config(signature_version="s3v4"),
    )


def presigned_upload_url(key: str, content_type: str) -> str:
    return _client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": get_settings().s3_bucket,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=URL_EXPIRES_SECONDS,
    )


def presigned_download_url(key: str) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": get_settings().s3_bucket, "Key": key},
        ExpiresIn=URL_EXPIRES_SECONDS,
    )
