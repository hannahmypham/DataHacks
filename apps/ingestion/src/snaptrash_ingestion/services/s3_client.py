from __future__ import annotations
import boto3
from botocore.client import Config
from snaptrash_common import settings

_s3 = None


def s3():
    global _s3
    if _s3 is None:
        # Temp creds (Lambda IAM role) start with ASIA — don't pass them explicitly
        # or boto3 will use them without the required session token. Let boto3
        # resolve credentials via the standard chain (IAM role / env / ~/.aws).
        key = settings.AWS_ACCESS_KEY_ID
        use_explicit = bool(key) and not key.startswith("ASIA")
        _s3 = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=key if use_explicit else None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY if use_explicit else None,
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


RAW_BUCKET = "snaptrash-raw-incoming"


def presign_put_raw(
    restaurant_id: str,
    zip_code: str,
    neighborhood: str,
    ts: int,
    content_type: str = "image/jpeg",
    expires: int = 300,
) -> tuple[str, str]:
    """Return (presigned PUT URL, S3 key) for direct iOS → S3 upload.

    Key encodes metadata as path segments so Lambda can parse without head_object.
    Format: {restaurant_id}/{zip}/{neighborhood_urlencoded}/{ts}.jpg
    """
    from urllib.parse import quote
    ext = "jpg" if "jpeg" in content_type else content_type.split("/")[-1]
    nb_encoded = quote(neighborhood or "unknown", safe="")
    key = f"{restaurant_id}/{zip_code}/{nb_encoded}/{ts}.{ext}"
    url = s3().generate_presigned_url(
        "put_object",
        Params={"Bucket": RAW_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=expires,
    )
    return url, key


def get_object_bytes(key: str, bucket: str | None = None) -> bytes:
    """Get raw bytes from S3 object (used by Lambda for comparison)."""
    b = bucket or settings.S3_BUCKET
    response = s3().get_object(Bucket=b, Key=key)
    return response['Body'].read()


def copy_object(
    source_key: str,
    dest_key: str,
    source_bucket: str | None = None,
    dest_bucket: str | None = None,
) -> str:
    """Copy S3 object (e.g. from raw-incoming to analyzed bucket). Returns new URL."""
    src_b = source_bucket or settings.S3_BUCKET
    dst_b = dest_bucket or settings.S3_BUCKET  # update with dedicated analyzed bucket var if added to settings
    s3().copy_object(
        Bucket=dst_b,
        CopySource={"Bucket": src_b, "Key": source_key},
        Key=dest_key,
    )
    return f"https://{dst_b}.s3.{settings.AWS_REGION}.amazonaws.com/{dest_key}"
