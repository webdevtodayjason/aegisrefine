# Hermes Agent Integration

Aegis Refine should be presented as a Hermes Agent-operated business workflow, not only as a Hermes-derived model demo.

## Runtime Roles

- **Hermes Agent**: operator/runtime that receives an Aegis Refine job and loads the `aegis-refine` skill.
- **Nemotron 3 Ultra**: `nvidia/nemotron-3-ultra-550b-a55b`, the primary operations brain for roadmap, routing, cap/margin, and spend decisions.
- **Nemotron 3 Nano**: `nvidia/nemotron-3-nano-30b-a3b`, the latency/cost fallback for fast receipt generation and low-risk routing.
- **Nemotron 3.5 Content Safety**: `nvidia/nemotron-3.5-content-safety`, the safety gate for PII / unsafe-content review when raw or summarized safety evidence is available.
- **Aegis-14B**: data-governance specialist trained from Hermes 14B for dataset quality, risk, and refinement decisions.
- **Stripe**: capped Checkout earn rail and payment-to-job creation. Outbound agent spend is a Hermes-initiated Stripe Connect Transfer to the AINode compute vendor when approved; the backend independently verifies the returned Stripe object before recording execution.
- **AAR / Frontier Infra**: signed proof layer for what the agent did.
- **AInode / DGX Spark**: clustered local model serving environment.

## Installed Skill

Repo copy:

```bash
hermes/aegis-refine/SKILL.md
```

Hermes runtime copy:

```bash
~/.hermes/skills/aegis-refine/SKILL.md
```

Run a proof invocation:

```bash
hermes -z --skills aegis-refine "$(cat hermes/aegis-refine/templates/operator-prompt.md)"
```

## Private Operator Bridge

The production backend can dispatch paid/completed job phases to Hermes without
exposing a shell or terminal to the browser:

```bash
python3 hermes/operator_bridge.py
```

Recommended Dell deployment:

```bash
HERMES_OPERATOR_BIND=100.110.83.82 \
HERMES_OPERATOR_PORT=8765 \
HERMES_OPERATOR_TOKEN=<shared-secret> \
HERMES_TELEGRAM_TARGET=telegram \
python3 /home/sem/aegis-hermes-operator-bridge.py
```

Coolify/backend environment:

```bash
HERMES_OPERATOR_URL=http://100.110.83.82:8765/operate
HERMES_OPERATOR_TOKEN=<same-shared-secret>
HERMES_OPERATOR_TIMEOUT_SECONDS=90
```

The Dell bridge can pin a fast receipt model independently of the interactive
Hermes default:

```bash
HERMES_OPERATOR_MODEL=nvidia/nemotron-3-ultra-550b-a55b
HERMES_OPERATOR_PRIMARY_TIMEOUT_SECONDS=25
HERMES_OPERATOR_FALLBACK_MODEL=nvidia/nemotron-3-nano-30b-a3b
HERMES_CONTENT_SAFETY_MODEL=nvidia/nemotron-3.5-content-safety
```

The honest production pattern is Ultra primary, Nano fallback. Receipts record
which model actually ran. The bridge also records the Content Safety gate status;
if raw data was not sent to the model, the status must be `metadata_only` or
`pending`, not a claimed full scan.

The backend stores Hermes receipts as `audit_logs` rows:

- `hermes_operator_decision`
- `hermes_operator_unavailable`

Customers can see the latest stored receipt on `/jobs/{job_id}` and
`/jobs/{job_id}/operator`; admins can manually retry with
`POST /jobs/{job_id}/operator/dispatch`.

## Stripe Agent Spend

The honest spend path is:

```text
SpendTicket approved -> Hermes Agent aegis-refine skill -> Stripe Connect Transfer -> Aegis backend verification -> executed receipt
```

Required environment:

```bash
STRIPE_AGENT_SPEND_VENDOR_ACCOUNT=acct_...
MAX_AGENT_SPEND_CENTS=5000
```

Hermes may create the transfer with:

```bash
python hermes/aegis-refine/scripts/create_stripe_transfer.py \
  --job-id <job_id> \
  --ticket-id <ticket_id> \
  --amount-cents <approved_spend_cents> \
  --service ainode_compute \
  --purpose ocr_enrichment
```

The backend does not trust the agent's claim. It retrieves the returned `tr_...`
from Stripe, checks the destination against `STRIPE_AGENT_SPEND_VENDOR_ACCOUNT`,
checks `amount_cents <= approved_cap_cents`, records `livemode` from Stripe, and
only then marks the spend ticket executed. If verification fails, the ticket
stays approved/queued and no synthetic payment id is recorded.

## Demo Beat

For the video, show a terminal or Hermes UI line like:

```bash
hermes -z --skills aegis-refine "Operate paid Aegis Refine job 16 and return the operator decision."
```

Then cut back to the browser showing the live job, Stripe payment, Hermes operator receipt, spend gate, output, and signed certificate/receipt.

## Submission Wording

Use this stack line:

> Hermes Agent is the operator. It loads an Aegis Refine skill, uses `nvidia/nemotron-3-ultra-550b-a55b` as the operations brain for routing and cap/spend decisions, records `nvidia/nemotron-3-nano-30b-a3b` as the latency fallback, uses `nvidia/nemotron-3.5-content-safety` for the safety gate when evidence is available, calls Aegis-14B for dataset governance, earns through capped Stripe Checkout, spends through a capped Stripe Connect Transfer to AINode compute when approved, and leaves the customer with a refined dataset plus signed proof. Aegis independently verifies the transfer against Stripe before recording the spend receipt.

Avoid saying Hermes Agent runs inside the production web container. The honest claim is that the backend dispatches job phases to the private Hermes Agent bridge on the Dell, Hermes runs the `aegis-refine` skill, and the app stores the returned operator receipt.
