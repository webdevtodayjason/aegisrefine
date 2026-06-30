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

## Demo Beat

For the video, show a terminal or Hermes UI line like:

```bash
hermes -z --skills aegis-refine "Operate paid Aegis Refine job 16 and return the operator decision."
```

Then cut back to the browser showing the live job, Stripe payment, spend gate, output, and signed certificate/receipt.

## Submission Wording

Use this stack line:

> Hermes Agent is the operator. It loads an Aegis Refine skill, uses Nemotron 3 Ultra for operational routing and cap/spend decisions, calls Aegis-14B for dataset governance, and leaves the customer with a refined dataset plus signed proof.

Avoid saying Hermes Agent runs inside the production web container unless that has been separately deployed and verified. The honest current claim is that Aegis Refine has a Hermes Agent skill and can dispatch/operate jobs through a running Hermes Agent instance.
