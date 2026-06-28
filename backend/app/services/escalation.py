"""Real paid inference escalation — the agent reaches OFF the free local Aegis-14B to the
cheapest-good-enough PAID model in the catalog ARSENAL when it flags a hard evaluation. This is
the agent's real SPEND, metered in tokens, gated by the cap.

Walks provider_catalog.ARSENAL_LADDER cheapest→most-capable and picks the first model whose
provider key is in env. NO keys ⇒ available()==[] and escalate() returns None, so the agent keeps
the free local result — an honest gated proposal, never a faked spend. Drop any provider key
(OPENAI/ANTHROPIC/ZAI/XAI/MINIMAX/MOONSHOT) and the SAME path makes one real, cap-bounded call.
"""
import os
from app.services import provider_catalog as pc


def available() -> list[str]:
    """ARSENAL providers whose API key is present in env."""
    return [name for name, p in pc.ARSENAL.items() if os.getenv(p["env_var"])]


def pick_model(capability: str = "hard/reasoning") -> str | None:
    """Cheapest-good-enough model on the ladder whose provider key is configured."""
    avail = set(available())
    for rung in pc.ARSENAL_LADDER.get(capability, []):
        if pc._ARSENAL_PROVIDER.get(rung["model"]) in avail:
            return rung["model"]
    return None


def source(api_id: str) -> str:
    return pc.ARSENAL_SOURCES.get(pc._ARSENAL_PROVIDER.get(api_id, ""), "catalog")


def estimate_cost(api_id: str, max_tokens: int = 512) -> float:
    """Conservative USD reserve for the cap check, priced at the catalog rate."""
    return round(pc.arsenal_cost(api_id, 2000, max_tokens), 6)


def escalate(messages, capability: str = "hard/reasoning", model: str | None = None, max_tokens: int = 512):
    """Make ONE real paid chat-completion call to the cheapest capable model with a key.
    Returns {text, provider, model, tokens, cost_usd, cost_source} or None if no key."""
    api_id = model or pick_model(capability)
    if not api_id:
        return None
    base, env = pc.arsenal_endpoint(api_id)
    key = os.getenv(env)
    if not key:
        return None
    from openai import OpenAI
    client = OpenAI(base_url=base, api_key=key)
    resp = client.chat.completions.create(model=api_id, messages=messages, max_tokens=max_tokens, temperature=0)
    u = resp.usage
    cost = pc.arsenal_cost(api_id, u.prompt_tokens, u.completion_tokens)
    return {"text": resp.choices[0].message.content, "provider": pc._ARSENAL_PROVIDER[api_id],
            "model": api_id, "tokens": {"in": u.prompt_tokens, "out": u.completion_tokens},
            "cost_usd": round(cost, 6), "cost_source": source(api_id)}
