# Aegis Quote + Budget Engine — buildable spec

Verified against live `backend/app` (2026-06-27). Real, dated provider prices; every quote/ledger
number computable. **Aegis-14B scores/decides; deterministic Python computes the price + runs the
ledger.** No model retrain (reuses the existing `triage` job). Companion to `CURATION_PLAN.md`.

## 1. The loop
```
/new-order → POST /jobs/quote {dataset_url,email} → quote_service.quote_job()   (NO Job, NO charge)
   Aegis-14B triage on a SAMPLE + deterministic price book → Quote card "$250 — capped, no surprises"
   [Accept & Pay] [Request change] [Decline]
 Accept → POST /jobs/ {quote_token} → verify HMAC+TTL → Stripe Checkout (unit_amount = quoted¢ = HARD CAP)
   → checkout.session.completed (signed webhook = the ONLY job creator)
   → create_paid_job(... quote) → Job{quote_amount, approved_cap=quote, target_margin_pct, quote_status}
   → refinery.process_job: before EVERY outbound provider call → budget_service.request_spend(provider,units)
        projected ≤ cap → autonomous (cheapest-good-enough); crosses soft margin line → reroute cheaper + log
        projected > cap → ARM HUMAN GATE (SpendTicket) → /admin/gate: re-quote | absorb | reject
   → complete_job → signed Ed25519 AAR records {quote, spent, margin, cap_respected, per-provider lines, output SHA-256}
```
Quote happens BEFORE any Stripe object exists (preserves the IDOR fix: payment, not the client, creates the Job).

## 2. Quote math (deterministic; reads Aegis-14B `triage` on a sample of K=min(2000, 1% of N))
```python
# COGS_est (real-priced, cheapest-good-enough routing) — the FLOOR + spend-budget basis
cost_tier(r)   = (t_in*price_in + t_out*price_out)/1e6
decide_per_rec = P*[(1-e)*cost_base + e*cost_next] + (pii ? cost_S : 0)     # e = escalation_fraction
C_decide = N*decide_per_rec*(1+retry)                                       # retry = min(0.10+malformed,0.25)
C_embed  = N*t_embed*0.01/1e6 ;  C_ocr = ocr_required ? pages*ocr_price[profile] : 0
C_human  = pii ? (scanned_doc?40:10):0 ;  C_fixed = 6.00
COGS_est = C_ocr + C_decide + C_embed + C_human + C_fixed                    # → Job.estimated_cost
# value list (OUR business price; only COGS inputs cite providers)
value_list = 9.00 + 1.50*(N/1000)*(1+c) + (C_ocr*1.30)
# cost floor (never sell below MARGIN_FLOOR on real cash cost)
cogs_floor = COGS_est/(1-0.55)
# pick, gross for Stripe, round UP
subtotal = max(value_list, cogs_floor)                                      # no flat project floor; data drives quote
charge   = (subtotal+0.30)/(1-0.029) ;  CAP = roundup(charge)               # <200:$5 · 200-1k:$10 · >1k:$50
requires_human_quote = (CAP > 1000)                                         # auto-quote only ≤ $1k
quote_amount = approved_cap = CAP ;  soft_margin_line = CAP*(1-0.65)        # soft = reroute+log, NOT a gate
# hard gate fires ONLY when projected provider spend > approved_cap
```
Token fallbacks (overridden by sampled `est_tokens`): jsonl 600/50/500 · tabular 200/40/150 · scanned-post-OCR 900/60/800.

**Worked examples (one formula, 3 binding constraints):**
- **A easy** 10k clean JSONL → COGS $6.21 → value binds → **CAP $30**, gate never arms.
- **B medium** 100k messy tabular+PII → COGS $20.43 → value binds → **CAP $250** (~88.8% margin), fully autonomous (80% on $0.02 Llama-8B, 20% ambiguous on gpt-4o-mini).
- **C hard** 20k scanned invoices (OCR $200 cash) → COGS $263 → **cost floor binds** → **CAP $610** (~53.9% ≈ floor). 200k-page version trips `requires_human_quote`.

## 3. Provider price book (`services/provider_catalog.py`; one source for quote + ledger; `_accessed 2026-06-27`)
```json
{ "ocr_per_page_usd":{"tesseract_selfhost":0.0,"textract_detect":0.0015,"textract_expense":0.010,
   "textract_forms":0.050,"gcp_docai_t1":0.0015,"gcp_docai_t2_over5m":0.0006},
  "per_1m_tokens_usd":{"aegis_14b_selfhost":[0,0],"llama31_8b":[0.02,0.05],"gpt_4o_mini":[0.15,0.60],
   "gpt_4_1_mini":[0.40,1.60],"nemotron_super_120b":[0.09,0.45],"deepseek_v3_2":[0.2288,0.3432],
   "claude_haiku_4_5":[1.0,5.0],"gpt_4_1":[2.0,8.0],"claude_sonnet_4_6":[3.0,15.0],"claude_opus_4_8":[5.0,25.0]},
  "embed_per_1m_usd":0.01, "stripe":{"pct":0.029,"flat":0.30},
  "image_tokens_per_page":{"input":1400,"output":800}, "discounts":{"batch":0.50,"prompt_cache":0.75} }
```
PRIME DIRECTIVE: **Aegis-14B / Tesseract / local DGX = $0 marginal, always tried first.** External = buy-it-at reference rates; each ladder rung runs only if the rung below returns low confidence. Sources: AWS Textract, Google Doc AI, OpenAI, Anthropic, OpenRouter/DeepInfra, DeepSeek (all accessed 2026-06-27). Per-page VLM cost is an estimate → meter real tokens on first N pages + recompute before committing the cap.

## 4. Budget ledger + overrun gate (`services/budget_service.py`; reuses SpendTicket — NO new table)
Ledger = `SUM(amount)` over a job's spend_tickets (Decimal, quantized to cents). `request_spend(db,job,provider,units,reason,capability)`:
- `SELECT…FOR UPDATE` the job (serialize concurrent calls so they can't collectively breach the cap).
- **projected > cap** → `create_spend_ticket` tagged `kind=gated, gate_reason=overrun:cap_exceeded` → `job.status=awaiting_approval` → return `('gated',t)` (AGENT BLOCKS).
- **projected ≤ cap** → if > soft_line, try `cheapest_good_enough` reroute + log `margin_warning`; then `create_spend_ticket` tagged `kind=autonomous` + `authorize_within_cap` → return `('authorized'|'rerouted',t)`.
- `authorize_within_cap`: actor=**agent**, action=`spend_preauthorized`, approved_by=`quote_pre_authorization#job:..#cap:$..` — **never impersonates a human**.
- `approve_overrun(mode in {absorb,recharge})`: real human via `approve_spend_ticket`; raises `approved_cap`; `recharge` adds a new Checkout to `revenue_collected`.

**Data-model deltas** (money stays `Float` for MVP; Decimal only in comparisons — integer-cents migration is owned v2):
- `Job`: `quote_amount, approved_cap, quote_status(draft|sent|accepted|declined|change_requested|expired), quote_breakdown(JSON), target_margin_pct=0.65, margin_floor_pct=0.55, revenue_collected, requires_human_quote, quote_accepted_at`. Reuse `estimated_cost`(projected COGS), `actual_cost`(executed ledger).
- `SpendTicket`: `kind(autonomous|gated), gate_reason, provider, units, unit_price_usd, cost_source, actual_amount`.

## 5. Cert economics (extends `aar_service.build_aar`; **block signing if `spent_usd > cap_usd`**)
```jsonc
"economics":{ "quoted_usd":250, "cap_usd":250, "revenue_collected_usd":250, "spent_usd":20.43,
  "stripe_fee_usd":7.55, "margin_usd":222.02, "realized_margin_pct":88.8, "target_margin_pct":65,
  "margin_floor_pct":55, "cap_respected":true,
  "providers":[{"name":"llama31-8b","rate_usd":0.05,"qty":4.0,"cost_usd":0.20,"source":"deepinfra.com/pricing","priced_on":"2026-06-27","kind":"autonomous"}],
  "overruns":[] },
"guarantees":{ "rows_in":100000,"rows_out":98700,"output_format":"sharegpt","schema_valid_pct":100,
  "pii_redacted":true,"output_sha256":"…" }
```
`cap_respected` is an issuance precondition. Every dollar recomputable from `units × unit_price_usd` against a cited source; every overrun names its human approver.

## 6. Wire-in (verified line refs)
| file | change |
|---|---|
| NEW `services/provider_catalog.py` | price book + `cost(provider, units)` |
| NEW `services/quote_service.py` | `quote_job(url,declared)`; `sign/verify_quote_token` (HMAC+15min TTL) |
| NEW `services/budget_service.py` | `ledger`, `request_spend` |
| `routers/jobs.py` L24–50 | ADD `POST /jobs/quote`; MODIFY `create_job` to take `quote_token`, replace `unit_amount:2000` with `round(quoted_usd*100)`, thread quote into metadata |
| `routers/webhooks.py` L32–40 | assert `amount_total==round(quoted_usd*100)`; `create_paid_job(...,quote)` |
| `services/job_service.py` L36 | `create_paid_job(db,url,email,quote)` sets quote_amount/approved_cap/quote_status/target_margin/estimated_cost |
| `services/spend_service.py` | add `authorize_within_cap`, `approve_overrun`; `execute_spend_ticket(...,actual_amount=None)` |
| `services/refinery.py` | gate provider calls via `request_spend`; `complete_job` computes spent/margin + line items |
| `services/aar_service.py` | add `economics`+`guarantees`; block signing if `spent>cap` |
| `routers/admin.py` `/admin/gate` | `/{id}/approve` accepts `mode` → `approve_overrun` |

## 7. MVP (ship Tue 2026-06-30) vs v2
**MVP:** provider_catalog + quote_service.quote_job + `POST /jobs/quote`; `create_job` charges the **real signed quote** (kills hardcoded `2000`); webhook asserts amount==quote; Job/SpendTicket columns; `budget_service.ledger`+`request_spend`+`authorize_within_cap`; cert economics+guarantees with `cap_respected`; one end-to-end demo on Example-B-shaped data (value-bound, gate never fires = the autonomy happy path). **Pairs with the curation MVP** (already built: `app/curate/`) so the cert hashes bytes Aegis produced.
**v2:** live overrun path (`approve_overrun`/re-quote Checkout); `execute_spend_ticket` real provider calls + `actual_amount` settlement; batch/prompt-cache discounts; integer-cents money migration (TRIPWIRE → Follow-Up Closet).

**Honesty risks:** (1) `value_list` is a business price, not market cost — labeled as such. (2) Money is Float → compare in Decimal-cents. (3) Never fake a human approval (autonomous=agent/`spend_preauthorized`; human=`approve_spend_ticket`). (4) SpendTicket authorizes OUR provider spend vs the cap, not a customer charge. (5) Per-page VLM cost is an estimate → meter + recompute. (6) `requires_human_quote` (>$1k) is the safety valve.

**Tunables:** `MARGIN_TARGET=0.65 · MARGIN_FLOOR=0.55 · FLOOR_BASE=0 · BASE=9 · RATE_PER_1K=1.50 · OCR_PASSTHROUGH=1.30 · C_FIXED=6 · ROUND=ceil(<200:5/200-1k:10/>1k:50) · HUMAN_QUOTE_CEILING=1000 · STRIPE=2.9%+0.30`
