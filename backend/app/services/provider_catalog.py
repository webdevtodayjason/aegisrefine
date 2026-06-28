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
