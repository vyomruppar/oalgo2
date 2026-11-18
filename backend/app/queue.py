"""Encrypted change queue for the free (GitHub Actions + Vercel) deployment.

The dashboard cannot write to the database directly in that setup, so every change (add a holding,
save settings, run a scan) is encrypted by the dashboard server and stored as a file in the public
repository's `oalgo-queue` branch. The next GitHub Actions run decrypts the files in order and replays
each one against the same API the local app uses, so validation and behaviour are identical.

Format: base64( iv[12] | AES-256-GCM ciphertext | tag[16] ), key = HMAC-SHA256(OALGO_SECRET, purpose).
Must match frontend/lib/ops.ts.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

QUEUE_PURPOSE = "oalgo2-queue-v1"


def derive(secret: str, purpose: str) -> bytes:
    if len(secret) < 32:
        raise ValueError("OALGO_SECRET must be at least 32 characters")
    return hmac.new(secret.encode(), purpose.encode(), hashlib.sha256).digest()


def derive_hex(secret: str, purpose: str) -> str:
    return derive(secret, purpose).hex()


def encrypt(obj: Any, key: bytes) -> str:
    iv = os.urandom(12)
    return base64.b64encode(iv + AESGCM(key).encrypt(iv, json.dumps(obj).encode(), None)).decode()


def decrypt(blob: str, key: bytes) -> Any:
    raw = base64.b64decode(blob.strip())
    return json.loads(AESGCM(key).decrypt(raw[:12], raw[12:], None))


# Changes the dashboard may queue: (method, path pattern). Anything else is rejected when replayed.
ALLOWED = [
    ("POST", r"^/api/scans$"),
    ("POST", r"^/api/holdings$"),
    ("PUT", r"^/api/holdings/\d+$"),
    ("DELETE", r"^/api/holdings/\d+$"),
    ("POST", r"^/api/holdings/import$"),
    ("PUT", r"^/api/config$"),
    ("POST", r"^/api/news/refresh(\?symbol=[A-Za-z.\-]{1,12})?$"),
]


def allowed(method: str, path: str) -> bool:
    import re
    return any(m == method and re.match(p, path) for m, p in ALLOWED)
