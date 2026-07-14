"""evidence_lib.py -- shared helpers for the MT5 evidence bridge.

Secret detection, account masking, SHA-256 checksums. Used by the exporter, the sync
guard, and the reconciler. Pure stdlib. No trading imports, no order calls.
"""
from __future__ import annotations

import hashlib
import re

EXPORTER_VERSION = "1.0.0"

# Patterns that must NEVER reach the evidence repo (Phase 3 refusal list).
SECRET_PATTERNS = [
    ("telegram_token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b")),
    ("github_token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b")),
    ("healthchecks_url", re.compile(r"https?://hc-ping\.com/[0-9a-fA-F-]{16,}")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("generic_secret", re.compile(r"(?i)\b(api[_-]?key|secret|passwd|password|access[_-]?token)\b\s*[:=]\s*\S{6,}")),
]


def scan_secrets(text: str) -> list[str]:
    """Return the names of any secret patterns found. Empty list = clean."""
    return [name for name, pat in SECRET_PATTERNS if pat.search(text or "")]


def assert_clean(text: str, where: str = "") -> None:
    hits = scan_secrets(text)
    if hits:
        raise ValueError(f"refusing to write {where}: contains likely secret(s) {hits}")


def mask_account(login: str | int) -> str:
    """Irreversible stable identifier for a broker login (no reversal to the number)."""
    return "acct_" + hashlib.sha256(str(login).encode()).hexdigest()[:12]


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()
