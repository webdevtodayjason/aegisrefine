"""Real, dated provider prices — the SINGLE source for the quote (quote_service) and the
ledger (budget_service). Aegis-14B / Tesseract / local DGX = $0 marginal, always tried first.

Prices accessed 2026-06-27 from each provider's official pricing page (see SOURCES).
Per-page VLM/OCR-by-token figures are estimates — meter real tokens on the first N pages and
recompute before committing the cap.
"""
ACCESSED = "2026-06-27"

OCR_PER_PAGE = {
    "tesseract_selfhost": 0.0, "textract_detect": 0.0015, "textract_expense": 0.010,
    "textract_forms": 0.050, "gcp_docai_t1": 0.0015, "gcp_docai_t2_over5m": 0.0006,
}

# (input, output) USD per 1M tokens
PER_1M_TOKENS = {
    "aegis_14b_selfhost": (0.0, 0.0), "llama31_8b": (0.02, 0.05), "gpt_4o_mini": (0.15, 0.60),
    "gpt_4_1_mini": (0.40, 1.60), "nemotron_super_120b": (0.09, 0.45), "deepseek_v3_2": (0.2288, 0.3432),
    "claude_haiku_4_5": (1.0, 5.0), "gpt_4_1": (2.0, 8.0), "claude_sonnet_4_6": (3.0, 15.0),
    "claude_opus_4_8": (5.0, 25.0),
}

EMBED_PER_1M = 0.01
STRIPE = {"pct": 0.029, "flat": 0.30}

SOURCES = {
    "textract": "aws.amazon.com/textract/pricing", "gcp_docai": "cloud.google.com/document-ai/pricing",
    "openai": "developers.openai.com/api/docs/pricing", "anthropic": "platform.claude.com/docs/.../pricing",
    "nemotron": "openrouter.ai/nvidia + deepinfra.com/pricing", "deepseek": "openrouter.ai/deepseek/deepseek-v3.2",
}


def token_cost(model: str, t_in: float, t_out: float) -> float:
    p_in, p_out = PER_1M_TOKENS[model]
    return (t_in * p_in + t_out * p_out) / 1e6


def ocr_cost(profile: str, pages: float) -> float:
    return pages * OCR_PER_PAGE[profile]


def cost(provider: str, units: float) -> float:
    """Generic cost for the ledger: OCR profiles bill per page, models bill per (already-summed)
    USD unit. Used by budget_service; the quote builds its own line items via token_cost/ocr_cost."""
    if provider in OCR_PER_PAGE:
        return ocr_cost(provider, units)
    return float(units)  # caller passes pre-computed USD for token-metered providers


# ══════════════════════════════════════════════════════════════════════════════════════
# ESCALATION ARSENAL — the PAID models Aegis-14B can reach OFF the free local DGX when it
# flags a hard eval it cannot do well locally. Same gated/metered/cap-bounded path as
# escalation.py: no provider key in env ⇒ that provider is unavailable() and we keep the
# free local result (honest no-spend fallback). All OpenAI-compatible chat endpoints.
#
# PRICE PROVENANCE: every [input, output] below is traceable to the 2026-06-27 researcher
# pull (ARSENAL_SOURCES). Prices the researchers marked uncertain/discrepant are listed in
# ARSENAL_UNCERTAIN — double-check those before relying on them. base_url + env_var are
# standard adapter config (NOT part of the price pull). Units: USD per 1,000,000 tokens.
# ══════════════════════════════════════════════════════════════════════════════════════

# provider -> {env_var, base_url, pricing_url, models{ api_id -> {px:[in,out], cap, ctx} }}
ARSENAL = {
    "openai": {
        "env_var": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
        "pricing_url": "https://developers.openai.com/api/docs/pricing",
        "models": {
            "gpt-4o":       {"px": [2.50, 10.00], "cap": "vision · multimodal flagship",            "ctx": 128_000},
            "gpt-4o-mini":  {"px": [0.15,  0.60], "cap": "cheap-bulk · vision-capable",             "ctx": 128_000},
            "gpt-4.1":      {"px": [2.00,  8.00], "cap": "generate · strong, 1M ctx",               "ctx": 1_047_576},
            "gpt-4.1-mini": {"px": [0.40,  1.60], "cap": "generate · mid balance, 1M ctx",          "ctx": 1_047_576},
            "gpt-4.1-nano": {"px": [0.10,  0.40], "cap": "cheap-bulk · floor price, 1M ctx (32k out cap)", "ctx": 1_047_576},
            "o3":           {"px": [2.00,  8.00], "cap": "reasoning · post ~80% price-cut",         "ctx": 200_000},
            "o4-mini":      {"px": [1.10,  4.40], "cap": "reasoning · cost-efficient",              "ctx": 200_000},
        },
    },
    "anthropic": {
        "env_var": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com/v1",   # OpenAI-compat layer
        "pricing_url": "https://platform.claude.com/docs/en/about-claude/pricing",
        "models": {
            "claude-opus-4-8":            {"px": [5.00, 25.00], "cap": "reasoning · current flagship Opus, 1M ctx", "ctx": 1_000_000},
            "claude-opus-4-7":            {"px": [5.00, 25.00], "cap": "reasoning · legacy Opus, 1M ctx",          "ctx": 1_000_000},
            "claude-opus-4-6":            {"px": [5.00, 25.00], "cap": "reasoning · legacy Opus, 1M ctx",          "ctx": 1_000_000},
            "claude-opus-4-5-20251101":   {"px": [5.00, 25.00], "cap": "reasoning · legacy Opus (alias claude-opus-4-5), 200k ctx", "ctx": 200_000},
            "claude-opus-4-1-20250805":   {"px": [15.00, 75.00], "cap": "reasoning · DEPRECATED old-tier price, retires 2026-08-05", "ctx": 200_000},
            "claude-sonnet-4-6":          {"px": [3.00, 15.00], "cap": "generate · production workhorse, 1M ctx", "ctx": 1_000_000},
            "claude-sonnet-4-5-20250929": {"px": [3.00, 15.00], "cap": "generate · legacy Sonnet (alias claude-sonnet-4-5), 200k ctx", "ctx": 200_000},
            "claude-haiku-4-5-20251001":  {"px": [1.00,  5.00], "cap": "cheap-bulk · fastest, near-frontier (alias claude-haiku-4-5)", "ctx": 200_000},
        },
    },
    "zai": {
        "env_var": "ZAI_API_KEY",
        "base_url": "https://api.z.ai/api/paas/v4",
        "pricing_url": "https://docs.z.ai/guides/overview/pricing",
        "models": {
            "glm-4.6":        {"px": [0.60, 2.20], "cap": "reasoning · flagship coding/reasoning, 200k ctx", "ctx": 200_000},
            "glm-4.5":        {"px": [0.60, 2.20], "cap": "reasoning · prior flagship, 128k ctx",            "ctx": 128_000},
            "glm-4.5-air":    {"px": [0.20, 1.10], "cap": "generate · lightweight value workhorse",          "ctx": 128_000},
            "glm-4.5v":       {"px": [0.60, 1.80], "cap": "vision · multimodal, 64k ctx",                    "ctx": 64_000},
            "glm-4.5-flash":  {"px": [0.00, 0.00], "cap": "cheap-bulk · FREE tier (rate-limited; legacy id glm-4-flash-250414)", "ctx": 128_000},
        },
    },
    "xai": {
        "env_var": "XAI_API_KEY",
        "base_url": "https://api.x.ai/v1",
        "pricing_url": "https://docs.x.ai/docs/models",
        "models": {
            "grok-4-0709":        {"px": [3.00, 15.00], "cap": "reasoning · LEGACY (alias grok-4), 256k ctx", "ctx": 256_000},
            "grok-3":             {"px": [3.00, 15.00], "cap": "generate · LEGACY (price disputed — see UNCERTAIN)", "ctx": 131_072},
            "grok-3-mini":        {"px": [0.30,  0.50], "cap": "cheap-bulk · LEGACY, light reasoning, low out-price", "ctx": 131_072},
            "grok-2-vision-1212": {"px": [2.00, 10.00], "cap": "vision · LEGACY multimodal, 32k ctx (single-source)", "ctx": 32_768},
        },
    },
    "minimax": {
        "env_var": "MINIMAX_API_KEY",
        "base_url": "https://api.minimax.io/v1",
        "pricing_url": "https://platform.minimax.io/docs/guides/pricing-paygo",
        "models": {
            "MiniMax-M2":      {"px": [0.30, 1.20], "cap": "reasoning · agentic/coding, 197k ctx (official rate; launch rate differs — see UNCERTAIN)", "ctx": 196_608},
            "MiniMax-Text-01": {"px": [0.20, 1.10], "cap": "generate · cheapest long-context, 1M ctx", "ctx": 1_000_000},
            "abab6.5s-chat":   {"px": [0.20, 0.20], "cap": "cheap-bulk · LEGACY/retired, LOW confidence — see UNCERTAIN", "ctx": 32_000},
        },
    },
    "moonshot": {
        "env_var": "MOONSHOT_API_KEY",
        "base_url": "https://api.moonshot.ai/v1",
        "pricing_url": "https://platform.kimi.ai/docs/pricing/chat",
        "models": {
            "kimi-k2.6":            {"px": [0.95, 4.00], "cap": "reasoning · current Kimi flagship, 262k ctx", "ctx": 262_144},
            "kimi-k2.5":            {"px": [0.60, 3.00], "cap": "reasoning · prior flagship, 262k ctx",        "ctx": 262_144},
            "kimi-k2.7-code":       {"px": [0.95, 4.00], "cap": "generate · agentic-coding, 262k ctx",        "ctx": 262_144},
            "kimi-k2-0711-preview": {"px": [0.55, 2.20], "cap": "generate · DEPRECATED, est price — see UNCERTAIN", "ctx": 131_072},
            "moonshot-v1-8k":       {"px": [0.20, 2.00], "cap": "cheap-bulk · legacy short-ctx text",          "ctx": 8_192},
            "moonshot-v1-32k":      {"px": [1.00, 3.00], "cap": "generate · legacy text",                      "ctx": 32_768},
            "moonshot-v1-128k":     {"px": [2.00, 5.00], "cap": "generate · legacy long-ctx text",             "ctx": 131_072},
            "kimi-latest":          {"px": [2.00, 5.00], "cap": "vision · est/LEGACY 128k tier — see UNCERTAIN", "ctx": 131_072},
        },
    },
}

# Flat lookups derived from ARSENAL (single source of truth above).
ARSENAL_PRICES = {aid: m["px"] for p in ARSENAL.values() for aid, m in p["models"].items()}  # api_id -> [in, out]
_ARSENAL_PROVIDER = {aid: name for name, p in ARSENAL.items() for aid in p["models"]}          # api_id -> provider key


# ── CHEAPEST-GOOD-ENOUGH decision ladder ────────────────────────────────────────────────
# Aegis-14B walks each ladder cheapest→most-capable and stops at the first model good enough
# for the job. (Prices shown are USD/1M [in, out], echoed from ARSENAL for traceability.)
ARSENAL_LADDER = {
    "cheap-bulk scoring": [   # high-volume classify / extract / score
        {"model": "glm-4.5-flash", "px": [0.00, 0.00], "pick_when": "massive volume, latency-tolerant; Z.ai free tier + rate limits acceptable → $0 marginal."},
        {"model": "gpt-4.1-nano",  "px": [0.10, 0.40], "pick_when": "need 1M ctx + dependable OpenAI infra at the floor paid rate; 32k output cap is fine."},
        {"model": "gpt-4o-mini",   "px": [0.15, 0.60], "pick_when": "bulk scoring must also READ images — cheapest vision-capable model."},
        {"model": "grok-3-mini",   "px": [0.30, 0.50], "pick_when": "bulk needs a little reasoning AND output volume dominates (lowest out-price)."},
        {"model": "claude-haiku-4-5-20251001", "px": [1.00, 5.00], "pick_when": "ceiling of cheap tier: need near-frontier judgment / extended thinking in bulk."},
    ],
    "mid judgment": [         # the 'generate' workhorse tier
        {"model": "glm-4.5-air",   "px": [0.20, 1.10], "pick_when": "default judge: cheapest capable generate model (Z.ai first-party rate)."},
        {"model": "gpt-4.1-mini",  "px": [0.40, 1.60], "pick_when": "need 1M ctx + OpenAI reliability for mid judgment."},
        {"model": "glm-4.6",       "px": [0.60, 2.20], "pick_when": "judgment shades into reasoning/coding; best value flagship."},
        {"model": "kimi-k2.6",     "px": [0.95, 4.00], "pick_when": "long-context (262k) agentic judgment over big inputs."},
        {"model": "gpt-4.1",       "px": [2.00, 8.00], "pick_when": "want a strong, broadly-trusted generate model."},
        {"model": "claude-sonnet-4-6", "px": [3.00, 15.00], "pick_when": "ceiling: top judgment quality, 1M ctx, adaptive thinking."},
    ],
    "hard/reasoning": [       # the model can't do it well locally — escalate to real reasoning
        {"model": "MiniMax-M2",    "px": [0.30, 1.20], "pick_when": "cheapest real reasoning; agentic/coding, 197k ctx."},
        {"model": "glm-4.6",       "px": [0.60, 2.20], "pick_when": "flagship reasoning/coding value, 200k ctx + cheap cache."},
        {"model": "o4-mini",       "px": [1.10, 4.40], "pick_when": "want an OpenAI reasoning chain at low cost."},
        {"model": "o3",            "px": [2.00, 8.00], "pick_when": "harder OpenAI reasoning, 200k ctx."},
        {"model": "grok-4-0709",   "px": [3.00, 15.00], "pick_when": "xAI reasoning, 256k ctx (legacy/enterprise access)."},
        {"model": "claude-opus-4-8", "px": [5.00, 25.00], "pick_when": "top of the arsenal: hardest evals, frontier reasoning, 1M ctx."},
    ],
    "vision": [               # image / scanned-doc understanding
        {"model": "gpt-4o-mini",   "px": [0.15, 0.60], "pick_when": "cheap, high-volume image reads."},
        {"model": "glm-4.5v",      "px": [0.60, 1.80], "pick_when": "vision value pick, 64k ctx (Z.ai first-party)."},
        {"model": "kimi-latest",   "px": [2.00, 5.00], "pick_when": "Moonshot-ecosystem vision (price UNCERTAIN — verify)."},
        {"model": "grok-2-vision-1212", "px": [2.00, 10.00], "pick_when": "xAI vision, small 32k ctx (legacy, single-source)."},
        {"model": "gpt-4o",        "px": [2.50, 10.00], "pick_when": "ceiling: best general multimodal flagship."},
    ],
}

# ── SOURCES (provider -> pricing_url @ access date) ──────────────────────────────────────
ARSENAL_SOURCES = {
    "openai":    "https://developers.openai.com/api/docs/pricing @ 2026-06-27",
    "anthropic": "https://platform.claude.com/docs/en/about-claude/pricing @ 2026-06-27",
    "zai":       "https://docs.z.ai/guides/overview/pricing @ 2026-06-27",
    "xai":       "https://docs.x.ai/docs/models @ 2026-06-27",
    "minimax":   "https://platform.minimax.io/docs/guides/pricing-paygo @ 2026-06-27",
    "moonshot":  "https://platform.kimi.ai/docs/pricing/chat @ 2026-06-27",
}

# ── UNCERTAIN — prices the researchers flagged; verify against a live account before trusting ──
ARSENAL_UNCERTAIN = {
    "grok-3":             "PRICE DISPUTE: $3/$15 (mem0, weighted authoritative) vs $2/$10 (aipricing.guru). Using $3/$15. Legacy.",
    "grok-2-vision-1212": "SINGLE-SOURCE $2/$10 (aipricing.guru only); 32k ctx not re-confirmed in 2026. Legacy.",
    "grok-4-0709":        "Dropped from official docs.x.ai list (legacy/enterprise access); $3/$15 + 256k agreed by aggregators.",
    "MiniMax-M2":         "Official pay-go now $0.30/$1.20; trackers still quote launch rate ~$0.255/$1.00 (197k ctx). Using official $0.30/$1.20.",
    "MiniMax-Text-01":    "$0.20/$1.10 strong 3rd-party agreement but NOT re-confirmed on official current page (older model). Low risk.",
    "abab6.5s-chat":      "LOW CONFIDENCE: retired family, only costbench lists ~$0.20/$0.20 (32k). No official page. Do not rely; contact MiniMax sales.",
    "kimi-latest":        "ESTIMATE/LEGACY: dropped from official index; $2/$5 = worst-case 128k tier of a dynamic alias. Verify in console.",
    "kimi-k2-0711-preview": "ESTIMATE/DEPRECATED: ~EOL 2026-05-25; ~$0.55/$2.20 (some sources $0.60/$2.50). Use kimi-k2.6 instead.",
    "glm-4.5-air":        "AGGREGATOR TRAP: ComputePrices/OpenRouter quote $0.13/$0.85 (reseller); Z.ai first-party is $0.20/$1.10 (used here).",
    "glm-4.5-flash":      "FREE ($0) is the official Z.ai rate; if a nonzero is needed, non-official reseller estimate ≈ $0.06/$0.40.",
}


def arsenal_price(api_id: str) -> list[float]:
    """[input, output] USD/1M for an arsenal api_id. Raises KeyError if unknown."""
    return ARSENAL_PRICES[api_id]


def arsenal_cost(api_id: str, t_in: float, t_out: float) -> float:
    """USD for t_in/t_out tokens at an arsenal api_id's rate."""
    p_in, p_out = ARSENAL_PRICES[api_id]
    return (t_in * p_in + t_out * p_out) / 1e6


def arsenal_endpoint(api_id: str) -> tuple[str, str]:
    """(base_url, env_var) the adapter would read to call this api_id."""
    p = ARSENAL[_ARSENAL_PROVIDER[api_id]]
    return p["base_url"], p["env_var"]


if __name__ == "__main__":
    # Offline self-check: every ladder entry resolves to a real arsenal model at the same price.
    for cap, rungs in ARSENAL_LADDER.items():
        for r in rungs:
            assert r["model"] in ARSENAL_PRICES, f"{cap}: unknown model {r['model']}"
            assert ARSENAL_PRICES[r["model"]] == r["px"], f"{cap}: {r['model']} price drift {r['px']} vs {ARSENAL_PRICES[r['model']]}"
    assert set(ARSENAL_SOURCES) == set(ARSENAL), "SOURCES/providers out of sync"
    assert all(k in ARSENAL_PRICES for k in ARSENAL_UNCERTAIN), "UNCERTAIN references an unknown api_id"
    print(f"provider_catalog.py arsenal self-check OK — {len(ARSENAL_PRICES)} models across "
          f"{len(ARSENAL)} providers; {len(ARSENAL_UNCERTAIN)} flagged uncertain.")
