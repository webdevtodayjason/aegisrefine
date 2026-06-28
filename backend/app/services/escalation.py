"""Real paid inference escalation — the agent reaches OFF the free local Aegis-14B to a more
capable PAID model when it flags a hard evaluation it can't do well locally. This is the agent's
real SPEND, metered in tokens, gated by the cap.

Uses an OpenAI-compatible endpoint (OpenRouter or NVIDIA build.nvidia.com). NO key in env ⇒
available()==[] and escalate() returns None, so the agent keeps the free local result — an honest
gated proposal, never a faked spend. Drop a key (OPENROUTER_API_KEY or NVIDIA_API_KEY) and the
SAME path makes one real, metered, cap-bounded call.
"""
import os
from app.services import provider_catalog as pc

# provider -> (base_url, env_var, default_model, catalog_key_for_pricing)
PROVIDERS = {
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
                   "nvidia/llama-3.1-nemotron-70b-instruct", "nemotron_super_120b"),
    "nvidia": ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY",
               "nvidia/llama-3.1-nemotron-70b-instruct", "nemotron_super_120b"),
}


def available() -> list[str]:
    return [p for p, (_, env, *_) in PROVIDERS.items() if os.getenv(env)]


def source(provider: str | None = None) -> str:
    provider = provider or (available() or ["openrouter"])[0]
    return f"{PROVIDERS[provider][0]}@{pc.ACCESSED}"


def estimate_cost(provider: str | None = None, max_tokens: int = 512) -> float:
    """Conservative USD reserve for the cap check (priced at the catalog rate)."""
    cat = PROVIDERS[provider or (available() or ["openrouter"])[0]][3]
    return round(pc.token_cost(cat, 2000, max_tokens), 6)


def escalate(messages, provider: str | None = None, model: str | None = None, max_tokens: int = 512):
    """Make ONE real paid chat-completion call. Returns {text, provider, model, tokens, cost_usd,
    cost_source} or None if no provider key is configured (honest no-spend fallback)."""
    provs = available()
    if not provs:
        return None
    provider = provider if provider in provs else provs[0]
    base, env, default_model, cat = PROVIDERS[provider]
    from openai import OpenAI
    client = OpenAI(base_url=base, api_key=os.getenv(env))
    resp = client.chat.completions.create(model=model or default_model, messages=messages,
                                          max_tokens=max_tokens, temperature=0)
    u = resp.usage
    cost = pc.token_cost(cat, u.prompt_tokens, u.completion_tokens)
    return {"text": resp.choices[0].message.content, "provider": provider, "model": model or default_model,
            "tokens": {"in": u.prompt_tokens, "out": u.completion_tokens},
            "cost_usd": round(cost, 6), "cost_source": source(provider)}
