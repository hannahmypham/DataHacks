from __future__ import annotations
import boto3
from botocore.client import Config
from snaptrash_common import settings

_s3 = None


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
            config=Config(signature_version="s3v4"),
        )
    return _s3


def upload_image(data: bytes, *, restaurant_id: str, ts: int, content_type: str = "image/jpeg") -> str:
    """Upload bytes to S3 and return a presigned URL (works with private buckets)."""
    ext = "jpg" if "jpeg" in content_type else content_type.split("/")[-1]
    key = f"{restaurant_id}/{ts}.{ext}"

    s3().put_object(
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
    )

    # Return presigned URL (valid for 1 hour) instead of public URL
    return presign_get(key, expires=3600)


def presign_get(key: str, expires: int = 3600) -> str:
    return s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": key},
        ExpiresIn=expires,
    )
