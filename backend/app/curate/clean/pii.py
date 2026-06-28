"""PII / secret masking — deterministic regex with typed placeholders.

The same PATTERNS are re-run on the OUTPUT by the verifier (residual must be 0) — that's what
makes "PII-safe" a re-checkable guarantee, not a claim. Presidio NER is the v2 precision upgrade.
"""
import re

# Order matters: more specific first so a number isn't half-masked by a looser rule.
PATTERNS = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("AWS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)")),
]


def mask_text(t: str):
    n = 0
    for label, pat in PATTERNS:
        t, c = pat.subn(f"[{label}]", t)
        n += c
    return t, n


def mask_record(rec: dict):
    total = 0
    for m in rec["messages"]:
        m["content"], c = mask_text(m["content"])
        total += c
    return rec, total


def residual_count(text: str) -> int:
    """Re-scan arbitrary text for any unmasked PII — used by the re-verifiable guarantee."""
    return sum(len(pat.findall(text)) for _, pat in PATTERNS)
