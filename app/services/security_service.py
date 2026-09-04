"""
Webhook security: HMAC signature verification.

Rate limiting and idempotency have been moved to `redis_store.py` to use
a durable, process-shared Redis backend. This module handles only the
stateless cryptographic signature check.
"""
import hmac
import hashlib
import logging

from app.config import settings

logger = logging.getLogger("aletheia")


def verify_webhook_signature(payload_bytes: bytes, signature_header: str | None) -> bool:
    """Verify the HMAC-SHA256 webhook signature.

    If `WEBHOOK_SECRET` is not configured, the check is skipped and all
    requests are accepted — appropriate for local development but not for
    production deployments.

    The expected header format is `sha256=<hex_digest>` (GitHub / Datadog style).
    Raw hex digests without the prefix are also accepted for compatibility.

    Args:
        payload_bytes: The raw (unparsed) request body bytes.
        signature_header: Value of the `X-Hub-Signature-256` header.

    Returns:
        True if the signature is valid (or if no secret is configured).
        False if the signature is missing or does not match.
    """
    if not settings.WEBHOOK_SECRET:
        # Open mode: no secret configured, allow all requests
        return True

    if not signature_header:
        logger.warning("Webhook received without X-Hub-Signature-256 header")
        return False

    # Strip "sha256=" prefix if present
    clean_sig = (
        signature_header.removeprefix("sha256=")
        if signature_header.startswith("sha256=")
        else signature_header
    )

    expected = hmac.new(
        settings.WEBHOOK_SECRET.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, clean_sig):
        logger.warning("Webhook signature mismatch — possible spoofed request")
        return False

    return True
