# Hermes Agent Integration

Aegis Refine should be presented as a Hermes Agent-operated business workflow, not only as a Hermes-derived model demo.

## Runtime Roles

- **Hermes Agent**: operator/runtime that receives an Aegis Refine job and loads the `aegis-refine` skill.
- **Nemotron 3 Ultra**: operations brain for roadmap, routing, cap/margin, and spend decisions when configured.
- **Aegis-14B**: data-governance specialist trained from Hermes 14B for dataset quality, risk, and refinement decisions.
- **Stripe**: capped checkout, payment-to-job creation, and governed spend rail.
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
HERMES_OPERATOR_MODEL=nvidia/nemotron-3-nano-30b-a3b
```

Use Ultra for a heavyweight operator demo shot when desired; use Nano for the
live receipt bridge when latency matters.

The backend stores Hermes receipts as `audit_logs` rows:

- `hermes_operator_decision`
- `hermes_operator_unavailable`

Customers can see the latest stored receipt on `/jobs/{job_id}` and
`/jobs/{job_id}/operator`; admins can manually retry with
`POST /jobs/{job_id}/operator/dispatch`.

## Demo Beat

For the video, show a terminal or Hermes UI line like:

```bash
hermes -z --skills aegis-refine "Operate paid Aegis Refine job 16 and return the operator decision."
```

Then cut back to the browser showing the live job, Stripe payment, Hermes operator receipt, spend gate, output, and signed certificate/receipt.

## Submission Wording

Use this stack line:

> Hermes Agent is the operator. It loads an Aegis Refine skill, uses Nemotron 3 Ultra for operational routing and cap/spend decisions, calls Aegis-14B for dataset governance, and leaves the customer with a refined dataset plus signed proof.

Avoid saying Hermes Agent runs inside the production web container. The honest claim is that the backend dispatches job phases to the private Hermes Agent bridge on the Dell, Hermes runs the `aegis-refine` skill, and the app stores the returned operator receipt.
