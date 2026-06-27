# Aegis API — live endpoint contract (for UI wiring)

> Captured from a real uvicorn run driven end-to-end (`scratchpad/http_e2e.py`), 2026-06-27.
> Base (dev): `http://127.0.0.1:8099`. All bodies JSON unless noted. Admin routes need `X-Admin-Key`.

## EARN
**`POST /jobs/`** — start an order, open Stripe Checkout. No Job is created here (webhook does that post-payment).
```
req : {"dataset_url": "https://…", "email": "buyer@…"}          # dataset_url must be https
resp: {"checkout_url": "https://checkout.stripe.com/c/pay/cs_test_…"}   # 400 if not https
```
**`POST /webhooks/stripe`** — Stripe-signed; Stripe calls it (not the UI). Verified `checkout.session.completed` → creates the Job.
```
resp: {"received": true, "job_id": 1}     # bad/missing signature -> 400
```

## OPERATE (governance — live Aegis-14B)
**`POST /jobs/{id}/process`** — run triage/quality/spend; arms the gate if the agent proposes a spend.
```
req : {"sample": "<dataset sample>", "hard_doc": "<optional edge case>"}
resp: {
  "triage":  {"complexity":48,"risk":60,"est_tokens":18000000,"noise_level":75,"steps":[…],"can_run_locally":true},
  "quality": {"quality_score":38,"issues":[…],"noise_level":…,"recommended_format":"chatml","est_clean_rows":…,"can_run_locally":…},
  "spend":   {"tool":"cloud_handwriting_ocr","reason":"…","est_cost_usd":120,"expected_gain":{…},"recommendation":"approve","rationale":"…"},
  "spend_ticket_id": 1            # present only when spend.recommendation == "approve"
}
```
(`process` may take a few seconds — it's live inference. A `reject` returns no `spend_ticket_id`.)

## GATE (human approval — `X-Admin-Key` required; `X-Admin-User` recorded as approver)
- **`GET /admin/gate/tickets`** → list of `proposed` SpendTickets.
- **`POST /admin/gate/{ticket_id}/approve`** → `{"status":"approved","ticket_id":1,"approved_by":"jason@…"}` (401 on bad/missing key).
- **`POST /admin/gate/{ticket_id}/reject`**  → `{"status":"rejected","ticket_id":1,"rejected_by":"…"}`.
- **`POST /admin/gate/{ticket_id}/execute`** → `{"status":"executed","ticket_id":1}` *(stub — real `@stripe/link-cli` lands in SPEND)*.

## PROVE (signed AAR)
**`POST /jobs/{id}/complete`** → finish + issue the signed certificate.
```
req : {"output": "<refined output text>"}
resp: {"job_id":1,"aar":"/jobs/1/aar","conformance_target":"L2","sig":{"alg":"Ed25519","by":"did:web:aegisrefine.com","value":"…"}}
```
**`GET /jobs/{id}/aar`** → the full signed AAR record (subject/principal/task/verdict/ground_truth/checks[]/verifier/issued/sig). Verifies **L2** via `node tools/aar.mjs verify <cert> --did-json public/.well-known/did.json`.
**`GET /.well-known/did.json`** → the DID document (public key) for independent verification.

## OPERATE / visualize
**`GET /activity?limit=50`** → newest-first redacted feed (the live ticker).
```
[{"at":"2026-06-27T22:11:46","action":"aar_issued","actor":"system","job_id":1,
  "summary":"Signed certificate issued ✓","details":{"response_sha256":"…","certificate_id":1}}, …]
```
Actions seen in a full run: `job_created → triage → quality → spend_decision → spend_proposed → spend_approved → spend_executed → aar_issued`. `details` is whitelisted (amount/model/cert/approver-handle) — never dataset_url/email/paths/PANs.

## Read (Dashboard / OrderDetail / Certificate)
- **`GET /jobs/?limit=N`** → `[{id,status,input,complexity_score,estimated_cost,created_at}]` (newest first).
- **`GET /jobs/{id}`** → `{id,status,input,output,complexity_score,estimated_cost,actual_cost,created_at, spend_tickets:[{id,amount,description,status,approved_by}], certificate:{id,aar}|null}`.

## Misc
`GET /health` → `{"status":"healthy"}`. The branded site is served at `/app/…` (same-origin); brand assets at `/brand-assets/…`.
