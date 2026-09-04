import hmac
import hashlib
import time
import logging
from typing import Dict
from fastapi import Request, HTTPException, status
from app.config import settings

logger = logging.getLogger("aletheia")

# In-memory rate limiting and idempotency token bucket store
_seen_idempotency_keys: Dict[str, float] = {}
_client_request_counts: Dict[str, list[float]] = {}

IDEMPOTENCY_TTL_SECONDS = 3600  # 1 hour
RATE_LIMIT_WINDOW = 60  # 60 seconds
MAX_REQUESTS_PER_WINDOW = 30


def verify_webhook_signature(payload_bytes: bytes, signature_header: str | None) -> bool:
    """Verify HMAC SHA-256 signature for inbound webhooks if WEBHOOK_SECRET is set."""
    if not settings.WEBHOOK_SECRET:
        return True  # Open in dev/unconfigured mode
    if not signature_header:
        return False

    # Extract signature format (e.g., sha256=xxx or raw hex)
    expected_prefix = "sha256="
    clean_sig = signature_header[len(expected_prefix):] if signature_header.startswith(expected_prefix) else signature_header

    mac = hmac.new(settings.WEBHOOK_SECRET.encode("utf-8"), payload_bytes, hashlib.sha256)
    computed_sig = mac.hexdigest()

    return hmac.compare_digest(computed_sig, clean_sig)


def check_idempotency_key(idempotency_key: str) -> bool:
    """Check if an idempotency key has been processed recently. Returns True if fresh, False if duplicate."""
    now = time.time()
    # Cleanup expired keys
    expired_keys = [k for k, t in _seen_idempotency_keys.items() if now - t > IDEMPOTENCY_TTL_SECONDS]
    for k in expired_keys:
        del _seen_idempotency_keys[k]

    if idempotency_key in _seen_idempotency_keys:
        return False

    _seen_idempotency_keys[idempotency_key] = now
    return True


def check_rate_limit(client_id: str) -> bool:
    """Basic sliding window rate limiter."""
    now = time.time()
    timestamps = _client_request_counts.get(client_id, [])
    # Remove timestamps older than window
    timestamps = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]

    if len(timestamps) >= MAX_REQUESTS_PER_WINDOW:
        return False

    timestamps.append(now)
    _client_request_counts[client_id] = timestamps
    return True
