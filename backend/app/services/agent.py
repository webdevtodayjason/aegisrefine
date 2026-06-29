"""
Aegis-14B agent client.

Calls the fine-tuned Hermes-4-14B (LoRA, ~257MB adapter) served by AInode on a DGX
Spark over Tailscale — an OpenAI-compatible endpoint. Aegis-14B is trained to emit
STRICT JSON for four jobs: quality, triage, spend, audit. This is the decision brain:
Conductor scores/routes deterministically, Aegis-14B makes the judgment, the human gates it.
"""

import os
import json
from openai import OpenAI

# REQUIRED — send this EXACT system message every call; the model was trained on it.
# NOTE: the deployed weights were trained with the literal string "Aegis-7B" (leftover
# from the earlier run). Keep it verbatim until Jason retrains/updates the prompt to
# "Aegis-14B" — then change the one token below. Mismatching it degrades the fine-tune.
AEGIS_SYSTEM_PROMPT = (
    "You are Aegis-7B, a governed dataset-refinery agent running locally on an "
    "NVIDIA DGX Spark. You analyze messy data and decide how to refine it into clean "
    "ShareGPT/ChatML training data. PRIME DIRECTIVE: prefer local processing; only "
    "propose an EXTERNAL paid tool when local methods genuinely cannot do the job; "
    "every external spend is gated by a human — never assume approval. Be conservative, "
    "precise, auditable. Always answer with STRICT JSON only, no prose."
)

# Required JSON keys per job — the schema reliability the eval measures, enforced at the app edge.
JOB_SCHEMAS = {
    "quality": ["quality_score", "issues", "noise_level", "recommended_format", "est_clean_rows", "can_run_locally"],
    "triage":  ["complexity", "risk", "est_tokens", "noise_level", "steps", "can_run_locally"],
    "spend":   ["tool", "reason", "est_cost_usd", "expected_gain", "recommendation", "rationale"],
    "audit":   ["decisions", "local_share_pct", "external_calls", "revenue_usd", "gated_spend_usd"],
}

JOB_SCHEMA_NOTES = {
    "quality": {
        "quality_score": "number from 0 to 1, or 0 to 10 if that is your calibrated scale",
        "issues": "array of short strings",
        "noise_level": "number from 0 to 1, or 0 to 100 if percentage-like",
        "recommended_format": "string, usually sharegpt or chatml",
        "est_clean_rows": "integer estimate",
        "can_run_locally": "boolean",
    },
    "triage": {
        "complexity": "number from 0 to 1, or 0 to 10 if that is your calibrated scale",
        "risk": "string or number describing dataset risk",
        "est_tokens": "integer token estimate",
        "noise_level": "number from 0 to 1, or 0 to 100 if percentage-like",
        "steps": "array of short local processing steps",
        "can_run_locally": "boolean",
    },
    "spend": {
        "tool": "string external tool/provider name, or none",
        "reason": "string",
        "est_cost_usd": "number",
        "expected_gain": "object or string",
        "recommendation": "approve or reject",
        "rationale": "string",
    },
    "audit": {
        "decisions": "array",
        "local_share_pct": "number",
        "external_calls": "array",
        "revenue_usd": "number",
        "gated_spend_usd": "number",
    },
}


class AgentError(ValueError):
    """The model did not return valid, schema-complete JSON for the job."""


class AegisTemporarilyQueued(RuntimeError):
    """Aegis-14B is temporarily unavailable; keep the job queued instead of falling back."""


def _clip_content(content: str | None, limit: int = 500) -> str:
    if content is None:
        return ""
    text = " ".join(str(content).replace("\x00", "").split())
    return text[:limit]


def schema_instruction(job: str) -> str:
    """Return an explicit per-job JSON contract to append to Aegis prompts."""
    if job not in JOB_SCHEMAS:
        raise ValueError(f"unknown job {job!r}; expected one of {list(JOB_SCHEMAS)}")
    notes = JOB_SCHEMA_NOTES[job]
    fields = ", ".join(f'"{k}"' for k in JOB_SCHEMAS[job])
    hints = "; ".join(f"{k}: {notes[k]}" for k in JOB_SCHEMAS[job])
    return (
        f"Return STRICT JSON only for job={job}. "
        f"Required top-level keys: {fields}. "
        f"Field notes: {hints}. "
        "Do not wrap the JSON in markdown. Do not omit any required key."
    )


def build_prompt(job: str, task_text: str) -> str:
    """Attach the JSON schema to every model request; the fine-tune still gets its familiar system prompt."""
    return f"{task_text}\n\n{schema_instruction(job)}"


def parse_decision(job: str, content: str) -> dict:
    """Parse + validate the model's structured output. Raises AgentError on bad shape."""
    if job not in JOB_SCHEMAS:
        raise ValueError(f"unknown job {job!r}; expected one of {list(JOB_SCHEMAS)}")
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError) as e:
        raise AgentError(f"{job}: model did not return valid JSON: {e}; raw={_clip_content(content)!r}") from e
    missing = [k for k in JOB_SCHEMAS[job] if k not in data]
    if missing:
        raise AgentError(f"{job}: response missing required fields {missing}; raw={_clip_content(content)!r}")
    return data


def _client() -> OpenAI:
    # AInode is OpenAI-compatible; auth currently off so any key works.
    return OpenAI(
        base_url=os.getenv("AINODE_API_URL", "http://localhost:8001/v1"),
        api_key=os.getenv("AINODE_API_KEY", "EMPTY"),
    )


def decide(job: str, task_text: str, *, model: str | None = None, retries: int = 1) -> dict:
    """Ask Aegis-14B for a structured decision; returns parsed, validated JSON.

    response_format=json_object makes vLLM guided-decode valid JSON; temperature=0 is
    deterministic; we still retry once on a schema miss — belt-and-suspenders for the demo.
    """
    if job not in JOB_SCHEMAS:
        raise ValueError(f"unknown job {job!r}; expected one of {list(JOB_SCHEMAS)}")
    client = _client()
    model = model or os.getenv("AINODE_MODEL", "Aegis-14B")
    last = None
    for _ in range(retries + 1):
        r = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": AEGIS_SYSTEM_PROMPT},
                {"role": "user", "content": build_prompt(job, task_text)},
            ],
            temperature=0,
            max_tokens=512,
            response_format={"type": "json_object"},
        )
        try:
            return parse_decision(job, r.choices[0].message.content)
        except AgentError as e:
            last = e
            continue
    raise AgentError(f"Aegis-14B failed to return valid {job} JSON after retries: {last}")


if __name__ == "__main__":
    # Offline self-check of the parse+validate logic (no network).
    ok = json.dumps({
        "tool": "mathpix", "reason": "scanned tables", "est_cost_usd": 2.5,
        "expected_gain": {"quality_pct": 12, "noise_pct": -8, "signal_pct": 5},
        "recommendation": "approve", "rationale": "local OCR cannot read these scans",
    })
    assert parse_decision("spend", ok)["recommendation"] == "approve"
    for bad_job, bad in [("spend", json.dumps({"tool": "x"})), ("triage", "not json{")]:
        try:
            parse_decision(bad_job, bad)
            raise SystemExit(f"FAIL: accepted bad {bad_job} output")
        except AgentError:
            pass
    try:
        parse_decision("bogus", ok)
        raise SystemExit("FAIL: accepted unknown job")
    except ValueError:
        pass
    print("agent.py self-check OK — strict-JSON schema validation working for", list(JOB_SCHEMAS))
