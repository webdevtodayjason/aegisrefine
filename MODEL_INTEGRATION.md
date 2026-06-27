# Aegis-14B — Model Integration (for the coding agents)

> Living doc. Owner: model/serving lane (Claude Code on the AInode side). Update on every
> endpoint/version change. **The app talks to one OpenAI-compatible endpoint; only the host
> changes between dev and final.**

## Status (2026-06-27) — COMPLETE
- ✅ **Trained**: `Aegis-14B` = LoRA fine-tune of `NousResearch/Hermes-4-14B` (Qwen3-14B, ~14.8B params), merged.
- ✅ **Verified**: held-out 48 → 100% valid JSON, 91% schema-correct.
- ✅ **Serving (AWQ, production)**: on **Spark-1** via vLLM (TRITON attention). Endpoint below.
- ✅ **Hugging Face**: published public → **https://huggingface.co/jbrashear/Aegis-14B** (bf16 full weights + model card; the AWQ build is what's served on Spark-1).

> ⚠️ It is a **14B** model (Hermes-4-14B base). Do not label it "7B" anywhere (the earlier
> "Aegis-7B" working name was wrong). The served-model-name is **`Aegis-14B`**.

## Endpoint — LIVE on Spark-1 (2026-06-27)
| Field | Value |
|---|---|
| Base URL (backend on Spark-1) | `http://localhost:8001/v1` ✅ |
| Base URL (remote/Tailscale) | `http://100.122.26.9:8001/v1` (Spark-1 head tailnet) |
| Model name | `Aegis-14B` |
| Protocol | OpenAI-compatible (`/v1/chat/completions`) — use the `openai` SDK |
| Auth | `Authorization: Bearer EMPTY` (AInode auth off) |
| Build serving now | **bf16** merged (verified). **AWQ** build swaps in at the SAME URL when its quant finishes (faster decode) — no code change. |

## System prompt (REQUIRED — send VERBATIM as the `system` message on every call)
⚠️ **Send this EXACTLY, including the literal "Aegis-7B" self-name.** The current weights were
fine-tuned with this exact string in all 481 examples; changing the self-name to "Aegis-14B"
is a distribution mismatch against the trained weights. The *product/repo/served-model-name*
is `Aegis-14B`, but the **system-prompt self-name stays `Aegis-7B` until we retrain** with the
corrected prompt (then this flips — one line).
```
You are Aegis-7B, a governed dataset-refinery agent running locally on an NVIDIA DGX Spark. You analyze messy data and decide how to refine it into clean ShareGPT/ChatML training data. PRIME DIRECTIVE: prefer local processing; only propose an EXTERNAL paid tool when local methods genuinely cannot do the job; every external spend is gated by a human — never assume approval. Be conservative, precise, auditable. Always answer with STRICT JSON only, no prose.
```

## The four jobs → output schemas (validate the matching shape)
| Job | `user` message is… | Returns JSON keys |
|---|---|---|
| **quality** | a raw/messy data sample or description | `quality_score, issues[], noise_level, recommended_format, est_clean_rows, can_run_locally` |
| **triage** | a job request (data + goal) | `complexity, risk, est_tokens, noise_level, steps[], can_run_locally` |
| **spend** | a mid-job edge case | `tool, reason, est_cost_usd, expected_gain{quality_pct,noise_pct,signal_pct}, recommendation("approve"|"reject"), rationale` |
| **audit** | a completed-job summary | `decisions[{step,choice,why}], local_share_pct, external_calls, revenue_usd, gated_spend_usd` |

The model emits the schema matching the task in the prompt; the app should know which job it's invoking so it validates the right keys.

## How to call (Python)
```python
import json
from openai import OpenAI
client = OpenAI(base_url="http://10.100.0.14:8001/v1", api_key="EMPTY")

resp = client.chat.completions.create(
    model="Aegis-14B",
    messages=[{"role": "system", "content": AEGIS_SYSTEM_PROMPT},
              {"role": "user",   "content": task_text}],
    temperature=0,                               # deterministic structured output
    max_tokens=512,
    response_format={"type": "json_object"},     # vLLM guided JSON → forces valid JSON
)
data = json.loads(resp.choices[0].message.content)   # still wrap in try/except + 1 retry
```

## Robustness
- `temperature=0` + `response_format={"type":"json_object"}` (vLLM guided decoding enforces valid JSON).
- Still wrap `json.loads` in try/except with one retry — belt-and-suspenders for the demo.
- The conservative bias is trained in: for the **spend** job it defaults to "reject / do it locally" unless local genuinely can't (the human-gate moment only fires on a real edge case).

## Provenance
- Base: `NousResearch/Hermes-4-14B` (Hermes 4 line; Qwen3-14B base; function-calling/JSON-tuned). License inherits from the base — credit on the HF card.
- Method: LoRA (r=16, α=32, all attn+MLP projections), 3 epochs on 433 synthetic ShareGPT examples (the 4 jobs, balanced), bf16 on one DGX Spark. 48 held out for eval.
- GB10 serving note: must launch vLLM with `--attention-backend TRITON_ATTN --enforce-eager` (FlashInfer hangs at load on GB10/sm121).

## Eval results (held-out 48, 2026-06-27)
- **Valid JSON: 48/48 (100%)** — always parseable.
- **Schema match: 44/48 (91%)** — audit 9/9, spend 7/7, quality 9/10, triage 19/22.
- In the app, `response_format=json_object` makes parseable JSON effectively 100%.
- Verified on the bf16 merge; AWQ build (served on Spark-1) is the production endpoint.
