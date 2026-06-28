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


# synthesis COGS: ~4 reasoning-model calls per candidate, divided by yield -> per high-value (Δ=1) row.
# ponytail: flat estimate; tune SYNTH_COST_PER_KEPT from real-run telemetry (by_model_usd / kept).
SYNTH_COST_PER_KEPT = 0.05


def quote_synth(target_kept: int, *, margin: float = MARGIN_TARGET) -> dict:
    """Price a synthesize/augment job: target high-value rows -> est COGS -> capped flat quote.
    More target rows => more compute => higher cap. estimated_cost is the private COGS bar."""
    cogs = round(target_kept * SYNTH_COST_PER_KEPT, 2)
    quote = round(max(FLOOR_BASE, cogs / (1 - margin)), 2)
    return {"quote_usd": quote, "estimated_cost_usd": cogs, "target_kept": target_kept,
            "target_margin_pct": round(margin * 100, 1), "service": "synthesis"}


# --- tamper-proof quote token (HMAC over the binding fields + TTL) ---

def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def sign_quote_token(quote: dict, dataset_url: str, email: str, now: int) -> str:
    body = _b64(json.dumps({"q": quote["quoted_usd"], "url": dataset_url, "email": email,
                            "exp": now + TOKEN_TTL}, sort_keys=True).encode())
    sig = _b64(hmac.new(_SECRET, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def sign_synth_token(quote: dict, topic: str, target_kept: int, reference: str, email: str, now: int) -> str:
    """Same HMAC+TTL envelope as a refine token, but binds the synthesis job params instead of a url."""
    body = _b64(json.dumps({"q": quote["quote_usd"], "service": "synthesis", "topic": topic,
                            "target_kept": int(target_kept), "reference": reference, "email": email,
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


# --- integration: sample the dataset, ask Aegis-14B to score complexity, price it ---

def _sample_features(dataset_url: str) -> dict:
    import urllib.request
    from app.curate import detect as cdetect
    from app.curate.parsers import dataset as cds, tabular as ctab
    from app.curate.clean.pii import residual_count

    with urllib.request.urlopen(dataset_url, timeout=30) as r:
        text = r.read().decode("utf-8", "replace")
    fmt = cdetect.detect(dataset_url, text[:512].encode("utf-8", "replace"))
    if fmt == "json":
        recs, dtype = cds.parse_json(text, dataset_url), "jsonl"
    elif fmt in ("csv", "tsv"):
        recs, dtype = ctab.parse_csv(text, dataset_url, "\t" if fmt == "tsv" else ","), "tabular"
    else:
        recs, dtype = cds.parse_jsonl(text, dataset_url), "jsonl"
    sample = recs[:8]
    sample_text = "\n".join(m["content"][:200] for rec in sample for m in rec["messages"])[:2000]
    pii = residual_count("\n".join(m["content"] for rec in sample for m in rec["messages"])) > 0
    return {"n_records": len(recs), "data_type": dtype, "pii": pii, "sample_text": sample_text}


def quote_job(dataset_url: str, email: str, now: int) -> dict:
    """Public: sample the dataset, get Aegis-14B's complexity read, return a signed capped quote.
    Model unreachable → deterministic heuristic complexity (flagged); never blocks a quote."""
    from app.services import agent
    f = _sample_features(dataset_url)
    complexity, scored_by = 0.4, "heuristic"
    try:
        tri = agent.decide("triage", f"Estimate complexity 0-1 for refining this {f['data_type']} "
                           f"dataset of ~{f['n_records']} records into clean ShareGPT/ChatML. "
                           f"Sample:\n{f['sample_text']}")
        c = float(tri.get("complexity") or 0.4)
        complexity, scored_by = max(0.0, min(1.0, c / 10 if c > 1 else c)), "aegis-14b"
    except Exception:
        pass
    q = price_quote(n_records=max(1, f["n_records"]), complexity=complexity, data_type=f["data_type"],
                    pii=f["pii"], passes=2 if f["pii"] else 1,
                    escalation_fraction=0.20 if complexity > 0.4 else 0.0, malformed_rate=0.05)
    q.update({"data_type": f["data_type"], "n_records": f["n_records"], "complexity": round(complexity, 3),
              "complexity_scored_by": scored_by, "dataset_url": dataset_url})
    q["token"] = sign_quote_token(q, dataset_url, email, now)
    return q
