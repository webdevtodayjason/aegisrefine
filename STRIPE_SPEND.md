# Stripe SPEND — verified Phase-2 build spec (the outbound/"agent buys what it needs" leg)

> Grounded by recon `wf_b0356d86` (4 readers + adversarial verify, 2026-06-27). Real-vs-announced
> is load-bearing — a payment-savvy judge will catch overclaims. Keep "used" vs "inspired-by" honest.

## What Stripe is actually going for
Make any AI agent a first-class payer via a **scoped, human-approved, revocable, single-use credential per purchase + a receipt as proof** — the agent never holds a reusable card. Aegis nails it: **gate every outbound buy behind one human tap, bind the whole ticket→receipt chain in a signed AAR** that proves money moved on approve and nothing moved on deny.

## ⏰ DECIDE ON DAY 1 (Jason) — live vs test money
- **Test mode** proves the mechanism end-to-end and is universal/reliable. Default.
- **Live money** needs the approver to hold a **US Link account + phone app**, OR an **enabled + funded Stripe Issuing program** — Stripe approval **can exceed 3 days**. Deadline is Tue 6/30. **If we want a live-money beat, start the Stripe Issuing/Link enablement NOW.** Don't discover the gate on day 3.

## The rail (BUILD ON — verified real, test-mode today)
- **`@stripe/link-cli` v0.8.2** (npm): `spend-request create --request-approval` = phone-push human gate (10-min window, 12h credential); `--test` (card 4242); `--output-file` PAN safety (0600); `mpp pay` for HTTP-402 merchants.
- **Stripe Issuing** (GA US/UK/EEA): `issuing_authorization.request` real-time webhook (~2s), and **`test_helpers`** approve→Transaction / deny→no-Transaction — the **deterministic, no-phone proof harness**.

## Spend flow (maps to `execute_spend_ticket`)
1. **Aegis-14B emits a SpendTicket** — vendor, amount(cents), ≥100-char justification naming the refinery gap (doc_id), line items. (The proposal artifact the AAR binds. No money yet.)
2. **Create the gated request:** `link-cli spend-request create --merchant-name … --merchant-url … --context "<≥100 chars>" --amount 50 --line-item … --total … --request-approval --test` → phone push, prints `lsrq_…`, polls.
3. **Human taps Approve/Deny** (10-min window). **GATE LOGIC: pay only if `exit==0 AND status=="approved"`.** Deny = `exit 0 + status:"denied"` (no card). Any non-zero (POLLING_TIMEOUT) = do-not-pay, **never blind-retry**.
4. **Retrieve credential PAN-safely:** `link-cli spend-request retrieve lsrq_… --include card --output-file /secure/card.json` (0600). stdout shows only brand/last4/expiry. **Never `--include card` without `--output-file`** (leaks PAN to transcript).
5. **Pay the vendor** with the scoped credential (vendor checkout, or `link-cli mpp pay <url> --spend-request-id lsrq_…` for 402/MPP). Ingest the result back into the refinery.
6. **Report + sign AAR:** `link-cli report --outcome success --spend-request-id lsrq_…`; sign `AAR{ticket_id, proposer:Aegis-14B, approver_action, credential_id(redacted), charge/transaction_id|null, receipt, outcome}`. Approve-cert carries a real Stripe id; deny-cert carries `null + status:denied`. Both signed + verifiable.
7. **Parallel deterministic proof (Issuing test_helpers):** `POST /v1/issuing/cards type=virtual`; webhook `issuing_authorization.request` → `{approved:true}` within 2s; `POST /v1/test_helpers/issuing/authorizations` + `/capture` → real **Transaction** object + balance deduction. Deny path → `{approved:false}` → **no Transaction, balance unchanged.** This is the cleanest on-camera "deny moves nothing."

## How we prove it (three claims)
- **(a) bought what it needs:** before/after — local OCR returns empty text layer on the scanned PDF; after the purchased OCR, the same page yields clean text that flows back into the refinery. The ≥100-char reason ties spend to a named gap = a capability buy, not a contrived charge.
- **(b) real money moved:** Issuing test_helpers `capture` → real Transaction + balance drop (observable, GA today); AAR embeds that Stripe id + receipt. (Optional: one tiny LIVE charge if enablement clears before 6/30.)
- **(c) deny moves nothing:** two independent rails (link-cli deny → no card; Issuing deny → no Transaction) both show zero movement. The signed deny-cert (charge=null) proves the gate is sound in **both** directions.

## Credits (writeup — keep honest)
- **USE / "built on":** `@stripe/link-cli` (human-gated PAN-safe one-time credential) + Stripe Issuing (deterministic proof). If we wire the 402 leg: "built on the **Machine Payments Protocol (MPP)** open spec (Tempo + Stripe, CC0) via the `mppx` reference SDK on Tempo testnet"; optionally cite IETF `draft-ryan-httpauth-payment` (HTTP-402 lineage).
- **INSPIRED-BY (don't claim integration unless implemented):** **ACP** (OpenAI + Stripe, Apache-2.0, Beta) — our ticket→approval→scoped-token→complete shape "modeled on ACP's delegate_payment / Allowance pattern."
- **BANNED (torches credibility):** claiming ChatGPT Instant Checkout, SPT GA, live network rails (Visa/Mastercard/BNPL), Tempo mainnet, or Stripe endorsement. SPT API is **preview** (`2026-04-22.preview`, US-only) — name-drop, never depend.

## Nemotron 3 Ultra
YES, behind a governance interface: **Aegis-14B = named governance brain** (proposes tickets, quality gates, accepts/rejects output, signs AARs); **Nemotron 3 Ultra = swappable at-scale refinement workhorse.** "Aegis governs, workhorse executes." Strengthens (not dilutes) the fine-tune story + pleases the NVIDIA judge. Keep it behind the interface so swapping never touches governance / spend / AAR.

## NVIDIA OpenShell / NemoClaw wrap — the human gate, on the sponsor's runtime (recon `wf_eb4c87f5`)
NemoClaw = NVIDIA's Apache-2.0 (**ALPHA**) agent stack on **OpenShell**, a kernel-isolated sandbox (Landlock/seccomp + **deny-by-default egress proxy** + inference.local credential brokering). Hermes is a built-in harness. **One beat → all three judges.**

**Do this (S–M, ~1 day, on a DGX Spark — the one platform NVIDIA lists tested-without-limits):** sandbox-wrap ONLY the Stripe link-cli, not the FastAPI app, not the harness.
1. `uv tool install -U openshell` (or the install.sh).
2. ~15-line deny-by-default `network_policies` YAML, binary-scoped to the link-cli.
3. Run the spend via `openshell sandbox exec -n <name> -- <link-cli cmd>` — exit code propagates, so the orchestrator calls it exactly as today.

**The money shot:** Aegis attempts the purchase to a host NOT yet allowlisted → OpenShell proxy returns **403** → the blocked request surfaces in the `openshell term` TUI → operator approves → approval **hot-reloads** into the running session policy → purchase proceeds. **The human gate is NVIDIA OpenShell's policy proxy, not our code** — on DGX Spark, governing a Hermes-lineage model we fine-tuned. Judge line: *"the gate on agent spending isn't our code — it's NVIDIA OpenShell's policy proxy returning 403 and waiting for operator approval."*

**Egress allowlist:** `api.stripe.com:443` + the real Stripe host set (`checkout/files/q.stripe.com` — **capture from one live run, don't guess**) + vendor host, each binary-scoped to link-cli. Keep the purchase-target host OFF the allowlist so the first attempt 403s = the gate. `network_policies` is hot-reloadable (no recreate).

**DEFER to writeup (L, alpha day-killer):** making Aegis-14B the in-sandbox inference model via inference.local. If ever attempted, the CORRECT env (a recon reader fabricated v1; verify caught it): `NEMOCLAW_PROVIDER=custom` (NOT "compatible-endpoint"), `NEMOCLAW_ENDPOINT_URL=http://localhost:8000/v1` (NOT `NEMOCLAW_BASE_URL`; **must include `/v1`**). Rides the alpha inference.local bridge NVIDIA flags as still-hardening.

**Caveats:** both ALPHA (no SLA) — rehearse the exact box + **snapshot a known-good sandbox**. Verify hands-on: the exact Stripe egress host set + that link-cli TLS is plain HTTPS the L7 proxy can gate. Fallback if alpha fights: same 403→approve gate against a mock egress target.

## OPEN — which is THE visible gate? (Jason)
Three valid designs; pick one for the 90s (don't show two approvals):
- **A (NVIDIA-gate, recommended):** OpenShell egress 403→operator-approve IS the gate; link-cli executes (`--test`) once egress opens. NVIDIA rail does the safety work.
- **B (Stripe-gate):** Stripe pre-allowlisted; link-cli `--request-approval` phone tap is the gate; OpenShell is just the safe sandbox.
- **C (layered, writeup story):** OpenShell gates network + Stripe gates payment = defense-in-depth, but two approvals on camera.

## Top risks
exit-code semantics (deny is exit 0, not non-zero) · PAN leak without `--output-file` · test-mode "not real" discount (mitigate with Issuing Transaction proof + maybe 1 live charge) · LIVE lead time >3 days · preview-rail temptation (SPT/Tempo mainnet) · region gating (link-cli/SPT US-only; test path is the universal fallback) · over-crediting Nemotron · **OpenShell/NemoClaw alpha flakiness (snapshot a known-good sandbox; mock-egress fallback).**
