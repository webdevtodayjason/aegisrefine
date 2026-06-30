---
name: aegis-refine
description: Operate Aegis Refine dataset jobs.
version: 1.0.0
author: Jason Brashear
license: MIT
platforms: [macos, linux]
prerequisites:
  commands: [curl, python]
metadata:
  hermes:
    tags: [aegis, datasets, stripe, nvidia, hermes-agent]
    related_skills: []
---

# Aegis Refine Operator

Use this skill when Hermes Agent is asked to operate an Aegis Refine customer job: quote review, route planning, spend governance, dataset refinement oversight, synthetic augmentation oversight, or signed-delivery verification.

Hermes Agent is the operator. Aegis-14B is the Hermes-14B-derived data-governance specialist. `nvidia/nemotron-3-ultra-550b-a55b` is the primary operations brain for roadmap, routing, margin, and spend decisions. `nvidia/nemotron-3-nano-30b-a3b` is the documented latency/cost fallback for receipt generation. `nvidia/nemotron-3.5-content-safety` is the NVIDIA safety gate for PII / unsafe-content review when raw or summarized safety evidence is available. Stripe Checkout is the earn rail. Outbound spend is currently an auditable internal cap ledger/test stub, not a completed Stripe Skills outflow. AAR certificates are the proof surface.

## When To Use

- A paid Aegis Refine job needs an operator decision, roadmap, or quality gate.
- A dataset needs a cleaning/sanitization/refinement plan before work runs.
- A dataset needs a PII / unsafe-content safety gate before delivery.
- A synthetic augmentation job needs a model/tool plan and proof criteria.
- A spend ticket needs review against the accepted customer cap.
- A completed job needs receipt/certificate verification before delivery.

## Prerequisites

- Aegis Refine backend or live site is reachable.
- The job has a real customer, quote, or Stripe checkout session when money is involved.
- Aegis-14B health should be checked through `/agent/health` before making governance claims.
- Do not fabricate Stripe, spend, model, or certificate state. If a value cannot be verified, say it is unverified.

## How To Execute

1. Establish the job context:
   - job id
   - service: `refine` or `synthesis`
   - source kind: uploaded file, URL, or seed/reference dataset
   - accepted quote and hard cap
   - customer/account context if available
2. Check Aegis-14B reachability:
   - Live: `curl -fsS https://aegisrefine.com/agent/health`
   - Local: `curl -fsS http://localhost:8000/agent/health`
3. Build the operator decision:
   - classify data type and risk
   - record the Nemotron 3.5 Content Safety gate status
   - decide local refinement vs synthetic augment vs OCR/tool escalation
   - identify models/tools required
   - estimate spend and compare against the accepted cap
   - choose whether to continue, queue, request approval, or fail closed
4. Preserve receipts:
   - quote receipt
   - Stripe session/payment state
   - spend ticket decisions
   - audit events
   - AAR certificate id/link
5. For completed jobs, send Jason a concise Telegram receipt through Hermes messaging.
6. Produce a concise operator result in JSON only when called by the Aegis bridge.

## Reference Quick Commands

| Purpose | Command |
| --- | --- |
| Check production Aegis | `curl -fsS https://aegisrefine.com/agent/health` |
| Check local Aegis | `curl -fsS http://localhost:8000/agent/health` |
| Load this skill once | `hermes -z --skills aegis-refine "Operate Aegis Refine job <id>..."` |
| Run from repo prompt | `hermes -z --skills aegis-refine "$(cat hermes/aegis-refine/templates/operator-prompt.md)"` |
| Send Telegram receipt | `hermes send --to telegram "Aegis Refine job <id> completed: quote, spend, AAR"` |

## Operator Decision Schema

Return this JSON shape when operating a job:

```json
{
  "operator": "Hermes Agent",
  "skill": "aegis-refine",
  "job_id": null,
  "service": "refine",
  "aegis_health": "ok|degraded|unverified",
  "primary_models": {
    "operator": "Hermes Agent",
    "operations_brain": {
      "primary": "nvidia/nemotron-3-ultra-550b-a55b",
      "active": "nvidia/nemotron-3-ultra-550b-a55b",
      "fallback": "nvidia/nemotron-3-nano-30b-a3b",
      "fallback_used": false
    },
    "content_safety_gate": "nvidia/nemotron-3.5-content-safety",
    "data_governance": "Aegis-14B"
  },
  "safety_gate": {
    "model": "nvidia/nemotron-3.5-content-safety",
    "status": "passed|flagged|metadata_only|pending",
    "reason": null
  },
  "route": "run_local|synthesize|request_spend|temporarily_queue|fail_closed",
  "cap": {
    "quoted_usd": null,
    "approved_cap_usd": null,
    "projected_spend_usd": null,
    "cap_respected": null
  },
  "spend_decision": {
    "needed": false,
    "tool_or_model": null,
    "reason": null,
    "ticket_required": false
  },
  "proof": {
    "stripe_verified": false,
    "quote_receipt_verified": false,
    "aar_expected": true,
    "delivery_allowed": false
  },
  "next_action": "continue|queue|ask_operator|block_delivery"
}
```

## Procedure

### Refine Jobs

1. Use Aegis-14B for data-domain governance: quality, PII/noise risk, format, usable rows, and whether the data can be processed locally.
2. Use `nvidia/nemotron-3.5-content-safety` as the PII / unsafe-content safety gate when raw sample text or signed safety summaries are available.
3. Use `nvidia/nemotron-3-ultra-550b-a55b` for the operator roadmap when latency permits: business route, margin/cap reasoning, tool/model choice, and approval wording.
4. Use `nvidia/nemotron-3-nano-30b-a3b` only as the documented fast fallback for receipt generation or low-risk routing; do not label a Nano run as Ultra.
5. If local Aegis processing is enough, continue within cap.
6. If external spend is justified and within the accepted cap, create or approve an auditable spend ticket according to the Aegis Refine backend policy.
7. If projected spend exceeds the accepted cap, fail closed into a human approval/requote path.
8. Do not deliver if the refined output is empty or the certificate cannot be issued.

### Synthesis / Augment Jobs

1. Treat the uploaded/reference file as the grounding source.
2. Generate only examples that are plausibly useful for the target training task.
3. Keep provenance: target rows, candidates generated, rows kept, models used, and spend.
4. If zero rows are kept, fail the job instead of signing an empty deliverable.

### Receipts And Proof

Before calling a job complete, verify:

- The job belongs to the authenticated customer or an admin operator is reviewing it.
- Stripe payment or checkout state is attached when the job is paid.
- The accepted quote/cap is present.
- Spend tickets show proposed/approved/executed/rejected status.
- The safety gate status is recorded. If no raw data was sent to the content-safety model, mark it `metadata_only` or `pending` instead of claiming a full scan.
- Downloadable output is non-empty.
- AAR certificate exists or is explicitly pending.
- Telegram receipt was sent for completed jobs, or the send failure is reported without blocking delivery.

### Telegram Receipts

When a job phase is `completed`, send a short Telegram receipt through Hermes:

```sh
hermes send --to telegram "Aegis Refine job <id> completed: quote $<amount>, cap $<cap>, spend $<spent>, AAR <path>"
```

Never include raw dataset contents, PII, private customer data, or secrets in Telegram. Include only job id, service, route, quote/cap, executed spend, status, and the protected AAR/download location.

## Known Issues

- If `/agent/health` is degraded, do not run a fake fallback. Return `temporarily_queue`.
- If the web app is reachable but admin receipt endpoints require a browser session, report that the receipt is protected rather than guessing.
- If Stripe state is missing, do not claim the job earned revenue.
- If outbound spend lacks a Stripe payment intent, describe it as internal ledger/test-stub spend authorization, not Stripe Skills money movement.
- If `nvidia/nemotron-3-ultra-550b-a55b` is unavailable or too slow, record the actual fallback model. Do not write "Ultra" over a Nano run.
- If `nvidia/nemotron-3.5-content-safety` did not inspect raw/summarized safety evidence, report `metadata_only` or `pending`; do not claim it sanitized the data.

## Verification

Minimum proof for a demo:

1. Hermes Agent invocation shows `--skills aegis-refine`.
2. The skill returns `operator: Hermes Agent`.
3. `/agent/health` returns `model_name: Aegis-14B`.
4. The result names the route and cap decision.
5. The web app shows the matching job, spend/audit trail, output, or queued/failure state.
