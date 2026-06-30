---
base_model: NousResearch/Hermes-4-14B
library_name: peft
pipeline_tag: text-generation
tags:
  - aegis
  - dataset-refinery
  - function-calling
  - json-mode
  - lora
  - dgx-spark
  - nous-hermes
  - qwen3
  - agent
  - governance
---

# Aegis-14B

**A LoRA fine-tune of [NousResearch/Hermes-4-14B](https://huggingface.co/NousResearch/Hermes-4-14B) for autonomous dataset-job governance.**

Aegis-14B is the decision-and-signing model behind [Aegis Refine](https://aegisrefine.com), an agent-operated dataset refinery that turns messy training data into clean, certified datasets. Where a general agent runs the job, Aegis-14B governs it: it judges dataset quality and risk, chooses the refinement route, decides whether a paid step is justified within an approved budget, and signs the result.

It is purpose-trained for one role in a larger system, not as a general chat model. Built and served locally on NVIDIA DGX Spark.

> Messy data in. Signed data out.

## What It Does

Given a dataset job, source file/URL/seed, service type, accepted quote, and hard spend cap, Aegis-14B produces a structured operator decision:

- **Quality and risk triage**: assesses noise, duplication, PII exposure, and input complexity.
- **Route planning**: chooses `run_local`, `synthesize`, `request_spend`, `temporarily_queue`, or `fail_closed`.
- **Spend governance**: decides whether an over-base paid step, such as OCR, enrichment, or extra compute, is justified within the approved cap.
- **Proof discipline**: refuses to fabricate Stripe, spend, model, or certificate state; anything it cannot verify is labeled `unverified`.

It is designed to fail closed: if health is degraded or a proof step cannot be satisfied, it routes to `temporarily_queue` rather than inventing a successful path.

## Intended Output

Aegis-14B is prompted to return JSON matching the Aegis Refine operator schema:

```json
{
  "service": "refine | synthesis",
  "aegis_health": "ok | degraded | unverified",
  "route": "run_local | synthesize | request_spend | temporarily_queue | fail_closed",
  "cap": {
    "quoted_cents": 2000,
    "approved_cap_cents": 2000,
    "projected_spend_cents": 400,
    "cap_respected": true
  },
  "spend_decision": {
    "needs_spend_ticket": false,
    "reason": "within base budget"
  },
  "proof": {
    "stripe_verified": false,
    "quote_receipt": "preserved",
    "aar_certificate": "pending",
    "delivery_ok": false
  },
  "next_action": "continue | queue | ask_operator | block_delivery"
}
```

## Where It Fits

| Role | Component |
|---|---|
| Operator runtime | Hermes Agent running the `aegis-refine` skill |
| Data-domain governance and signing | Aegis-14B |
| Operations brain | `nvidia/nemotron-3-ultra-550b-a55b` |
| Latency fallback | `nvidia/nemotron-3-nano-30b-a3b` |
| PII / unsafe-content gate | `nvidia/nemotron-3.5-content-safety` |
| Money rails | Stripe Checkout earns; Stripe Connect Transfer spends |
| Proof layer | AAR signed certificate plus audit trail |

Full architecture: [aegisrefine.com/how-it-works.html](https://aegisrefine.com/how-it-works.html)

## Usage

Aegis-14B is a PEFT/LoRA adapter on top of Hermes 4 14B. Load the base model and apply the adapter:

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

base = "NousResearch/Hermes-4-14B"
adapter = "jbrashear/Aegis-14B"

tok = AutoTokenizer.from_pretrained(base)
model = AutoModelForCausalLM.from_pretrained(
    base,
    torch_dtype=torch.bfloat16,
    device_map="auto",
)
model = PeftModel.from_pretrained(model, adapter)

messages = [
    {
        "role": "system",
        "content": (
            "You are Aegis-14B, the governance model for Aegis Refine. "
            "Return ONLY the operator-decision JSON. Never fabricate payment, "
            "spend, or certificate state; label anything unverifiable as 'unverified'."
        ),
    },
    {
        "role": "user",
        "content": (
            "Job a1b2: service=refine, source=uploaded.jsonl "
            "(8420 rows, scanned PII likely), quoted=$20.00, "
            "approved_cap=$20.00, aegis_health=ok. Plan the route."
        ),
    },
]

prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = tok(prompt, return_tensors="pt").to(model.device)
out = model.generate(**inputs, max_new_tokens=512, temperature=0.2)
print(tok.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True))
```

Uses the Hermes 4 / ChatML chat template. Low temperature, at or below `0.3`, is recommended for stable, schema-valid JSON.

## Intended Use

- Governing dataset-refinement and synthetic-augmentation jobs inside the Aegis Refine pipeline.
- Producing auditable, structured decisions: route, cap, spend, proof, and next action.
- Research into governed, fail-closed agent decision-making and verifiable agent economics.

## Out Of Scope

- General-purpose chat or open-ended generation.
- Executing payments directly. Aegis-14B proposes and governs spend; Hermes Agent initiates configured Stripe actions, and the backend independently verifies the Stripe object before recording execution.
- Treating model output as proof on its own. Economic claims are checked against the system of record, such as Stripe, before they are trusted.

## Training Context

- **Base model:** [NousResearch/Hermes-4-14B](https://huggingface.co/NousResearch/Hermes-4-14B), Qwen3 architecture, approximately 14.7B parameters.
- **Method:** LoRA fine-tuning.
- **Hardware:** NVIDIA DGX Spark.
- **Task focus:** structured governance decisions for dataset-refinery jobs: route planning, spend-gate judgment, proof discipline, and signing readiness.

Formal evaluation metrics will be published separately when the schema-validity, route-accuracy, cap-respect, and refusal-to-fabricate tests are finalized. Until then, treat this as a project artifact and governance adapter rather than a benchmarked general model.

## Limitations And Responsible Use

Aegis-14B makes governance decisions; it does not by itself guarantee safe data. Its content-risk judgments are paired with a dedicated content-safety model and spend gating. As with any LoRA on a large base model, outputs should be validated against the expected JSON schema, and economic actions should be verified against the underlying system of record before being trusted.

## Ecosystem

- **Live product:** [aegisrefine.com](https://aegisrefine.com)
- **System map:** [aegisrefine.com/how-it-works.html](https://aegisrefine.com/how-it-works.html)
- **Open standards:** [Frontier Infra](https://frontierinfra.org/) - AVL for agent-readable sites, AAR for signed proof, ADL for disciplined agent logs.
- **Base model:** [NousResearch/Hermes-4-14B](https://huggingface.co/NousResearch/Hermes-4-14B)

Built for the Hermes Agent Accelerated Business Hackathon, presented by Nous Research, NVIDIA, and Stripe.

## Citation

```bibtex
@misc{aegis14b2026,
  title  = {Aegis-14B: A governance fine-tune of Hermes 4 14B for agent-operated dataset refinement},
  author = {Brashear, Jason},
  year   = {2026},
  howpublished = {\url{https://huggingface.co/jbrashear/Aegis-14B}}
}
```
