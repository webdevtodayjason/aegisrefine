"""Deterministic quote engine — turns dataset features (+ Aegis-14B triage) into ONE flat,
capped price. The model decides/scores; this code computes the number. See QUOTE_ENGINE.md.

`price_quote` is pure + testable (validated against the spec's 3 worked examples). `quote_job`
samples the dataset, calls Aegis-14B triage, and calls `price_quote`. HMAC tokens keep the client
from tampering with the amount between quote and Checkout.
"""
import os
import math
import json
import hmac
import time
import base64
import hashlib

from app.services import provider_catalog as pc

# --- tunables (QUOTE_ENGINE.md §7) ---
MARGIN_TARGET = 0.65
MARGIN_FLOOR = 0.55
FLOOR_BASE = 49.0
BASE = 9.0
RATE_PER_1K = 1.50
OCR_PASSTHROUGH = 1.30
C_FIXED = 6.00
HUMAN_QUOTE_CEILING = 1000.0
TOKEN_TTL = 15 * 60

# (t_in, t_out, t_embed) fallbacks by data type, overridden by sampled est_tokens
TOKENS = {"jsonl": (600, 50, 500), "tabular": (200, 40, 150), "scanned": (900, 60, 800)}

_SECRET = (os.getenv("SECRET_KEY") or "dev-only-secret").encode()


def _roundup(x: float) -> int:
    step = 5 if x < 200 else (10 if x <= 1000 else 50)
    return int(math.ceil(x / step) * step)


def price_quote(*, n_records, complexity, data_type="jsonl", pages=0, ocr_profile=None,
                escalation_fraction=0.0, passes=1, pii=False, scanned_doc=False,
                malformed_rate=0.0, base_model="llama31_8b", next_model="gpt_4o_mini",
                est_tokens=None) -> dict:
    N = n_records
    c = max(0.0, min(1.0, complexity))
    t_in, t_out, t_embed = est_tokens or TOKENS.get(data_type, TOKENS["jsonl"])

    cost_base = pc.token_cost(base_model, t_in, t_out)
    cost_next = pc.token_cost(next_model, t_in, t_out)
    cost_pii = pc.token_cost(base_model, t_in, t_out) if pii else 0.0
    decide_per_rec = passes * ((1 - escalation_fraction) * cost_base + escalation_fraction * cost_next) + cost_pii
    retry = min(0.10 + malformed_rate, 0.25)

    C_decide = N * decide_per_rec * (1 + retry)
    C_embed = N * t_embed * pc.EMBED_PER_1M / 1e6
    C_ocr = pc.ocr_cost(ocr_profile, pages) if ocr_profile else 0.0
    C_human = (40.0 if scanned_doc else 10.0) if pii else 0.0
    cogs = C_ocr + C_decide + C_embed + C_human + C_FIXED

    value_list = BASE + RATE_PER_1K * (N / 1000) * (1 + c) + C_ocr * OCR_PASSTHROUGH
    cogs_floor = cogs / (1 - MARGIN_FLOOR)
    subtotal = max(value_list, cogs_floor, FLOOR_BASE)
    charge = (subtotal + pc.STRIPE["flat"]) / (1 - pc.STRIPE["pct"])
    cap = _roundup(charge)

    return {
        "quoted_usd": float(cap), "cap_usd": float(cap),
        "estimated_cost_usd": round(cogs, 2),
        "value_list_usd": round(value_list, 2), "cogs_floor_usd": round(cogs_floor, 2),
        "target_margin_pct": MARGIN_TARGET * 100, "margin_floor_pct": MARGIN_FLOOR * 100,
        "soft_margin_line_usd": round(cap * (1 - MARGIN_TARGET), 2),
        "requires_human_quote": cap > HUMAN_QUOTE_CEILING,
        "breakdown": {"N": N, "complexity": round(c, 3), "data_type": data_type,
                      "C_ocr": round(C_ocr, 2), "C_decide": round(C_decide, 2),
                      "C_embed": round(C_embed, 4), "C_human": C_human, "C_fixed": C_FIXED},
        "priced_on": pc.ACCESSED,
    }


# --- tamper-proof quote token (HMAC over the binding fields + TTL) ---

def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def sign_quote_token(quote: dict, dataset_url: str, email: str, now: int) -> str:
    body = _b64(json.dumps({"q": quote["quoted_usd"], "url": dataset_url, "email": email,
                            "exp": now + TOKEN_TTL}, sort_keys=True).encode())
    sig = _b64(hmac.new(_SECRET, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_quote_token(token: str, now: int):
    try:
        body, sig = token.split(".")
        if not hmac.compare_digest(sig, _b64(hmac.new(_SECRET, body.encode(), hashlib.sha256).digest())):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return None if payload.get("exp", 0) < now else payload
    except Exception:
        return None
