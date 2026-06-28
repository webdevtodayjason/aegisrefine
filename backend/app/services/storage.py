"""R2 (S3-compatible) object storage — the durable home for ALL job files: user uploads, working/
scratch files, produced datasets, and signed certs. Nothing lives only on the container fs (which
is wiped on every redeploy). Per-user key prefixes. If no R2 creds are configured, enabled() is
False and callers fall back to the local fs / DB blob.

ponytail: stdlib + boto3, no wrapper framework. Cloudflare R2 is S3-compatible.
"""
import os
import uuid

_BUCKET = (os.getenv("R2_BUCKET") or "").strip()


def enabled() -> bool:
    return bool(_BUCKET and os.getenv("R2_ACCESS_KEY_ID") and os.getenv("R2_ENDPOINT"))


def _client():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("R2_ENDPOINT"),
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
        region_name=(os.getenv("R2_REGION") or "auto"),
    )


# --- per-user key helpers ---
def upload_key(user_id, filename: str) -> str:
    safe = "".join(c for c in (filename or "data") if c.isalnum() or c in "._-")[:80] or "data"
    return f"users/{user_id}/uploads/{uuid.uuid4().hex[:12]}-{safe}"


def job_key(user_id, job_id, name: str) -> str:
    """Working + output files for a job, e.g. job_key(u, j, 'dataset.sharegpt.jsonl')."""
    return f"users/{user_id}/jobs/{job_id}/{name}"


# --- ops (raise on real errors; callers decide fallback) ---
def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    _client().put_object(Bucket=_BUCKET, Key=key, Body=data, ContentType=content_type)
    return key


def get_bytes(key: str) -> bytes:
    return _client().get_object(Bucket=_BUCKET, Key=key)["Body"].read()


def exists(key: str) -> bool:
    try:
        _client().head_object(Bucket=_BUCKET, Key=key)
        return True
    except Exception:
        return False


def presign_get(key: str, expires: int = 3600) -> str:
    return _client().generate_presigned_url(
        "get_object", Params={"Bucket": _BUCKET, "Key": key}, ExpiresIn=expires)


def delete(key: str) -> None:
    _client().delete_object(Bucket=_BUCKET, Key=key)
