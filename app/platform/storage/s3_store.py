"""Async S3-compatible object storage client (AWS SigV4, no extra deps)."""

import hashlib
import hmac
import urllib.parse
from datetime import datetime, timezone

import aiohttp

from app.platform.logging.logger import logger


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _signing_key(secret_key: str, date_stamp: str, region: str) -> bytes:
    k = _sign(("AWS4" + secret_key).encode(), date_stamp)
    k = _sign(k, region)
    k = _sign(k, "s3")
    return _sign(k, "aws4_request")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_auth_headers(
    *,
    method: str,
    host: str,
    path: str,
    access_key: str,
    secret_key: str,
    region: str,
    payload: bytes,
    content_type: str,
) -> dict[str, str]:
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = _sha256_hex(payload)

    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    canonical_request = "\n".join([
        method,
        path,
        "",  # query string
        canonical_headers,
        signed_headers,
        payload_hash,
    ])

    credential_scope = f"{date_stamp}/{region}/s3/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256",
        amz_date,
        credential_scope,
        _sha256_hex(canonical_request.encode()),
    ])

    sig = _sign(_signing_key(secret_key, date_stamp, region), string_to_sign).hex()
    auth = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope},"
        f"SignedHeaders={signed_headers},Signature={sig}"
    )
    return {
        "Authorization": auth,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
        "Content-Type": content_type,
    }


class S3Store:
    """Minimal async S3-compatible PUT client."""

    def __init__(
        self,
        *,
        endpoint: str,
        region: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        path_prefix: str = "",
        custom_domain: str = "",
        upload_timeout: float = 300.0,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._region = region
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._prefix = path_prefix.strip("/")
        self._custom_domain = custom_domain.rstrip("/")
        self._timeout = upload_timeout

        parsed = urllib.parse.urlparse(self._endpoint)
        self._host = parsed.netloc or parsed.path

    def _s3_key(self, storage_path: str) -> str:
        storage_path = storage_path.lstrip("/")
        return f"{self._prefix}/{storage_path}" if self._prefix else storage_path

    def public_url(self, storage_path: str) -> str:
        key = self._s3_key(storage_path)
        if self._custom_domain:
            return f"{self._custom_domain}/{key}"
        return f"{self._endpoint}/{self._bucket}/{key}"

    async def upload(self, storage_path: str, data: bytes, content_type: str) -> str:
        """Upload *data* and return the public URL."""
        key = self._s3_key(storage_path)
        path = f"/{self._bucket}/{key}"
        headers = _build_auth_headers(
            method="PUT",
            host=self._host,
            path=urllib.parse.quote(path),
            access_key=self._access_key,
            secret_key=self._secret_key,
            region=self._region,
            payload=data,
            content_type=content_type,
        )
        url = f"{self._endpoint}{path}"
        async with aiohttp.ClientSession() as session:
            async with session.put(
                url,
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as resp:
                if resp.status not in (200, 201, 204):
                    body = await resp.text()
                    raise RuntimeError(f"S3 upload failed: HTTP {resp.status} — {body[:200]}")
        return self.public_url(storage_path)


_store: S3Store | None = None


def get_s3_store() -> S3Store | None:
    return _store


def init_s3_store(cfg: "Any") -> None:  # noqa: F821
    global _store
    storage_type = cfg.get_str("storage.type", "local")
    if storage_type != "s3":
        _store = None
        return
    _store = S3Store(
        endpoint=cfg.get_str("storage.s3.endpoint", ""),
        region=cfg.get_str("storage.s3.region", "us-east-1"),
        access_key=cfg.get_str("storage.s3.access_key", ""),
        secret_key=cfg.get_str("storage.s3.secret_key", ""),
        bucket=cfg.get_str("storage.s3.bucket", "grok-media"),
        path_prefix=cfg.get_str("storage.s3.path_prefix", "grok/"),
        custom_domain=cfg.get_str("storage.s3.custom_domain", ""),
        upload_timeout=cfg.get_float("storage.s3.upload_timeout", 300.0),
    )
    logger.info("S3 storage initialised: bucket={} endpoint={}", _store._bucket, _store._endpoint)


__all__ = ["S3Store", "get_s3_store", "init_s3_store"]
