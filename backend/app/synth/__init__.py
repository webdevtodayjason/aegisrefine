"""Synthetic data generation — Meta AutoData "Agentic Self-Instruct" loop, as a metered service.

Challenger generates tasks -> weak + strong solvers answer -> a Judge grades both ->
keep Delta = I_strong - I_weak = 1 (strong solves, weak fails = high-value training pairs).
Every model call is real + metered + budget-capped; output is LABELED synthetic and the cert
records the provenance. The Judge is Aegis-14B when reachable (its trained role), else a paid
model. The generator/solvers are paid arsenal models — Aegis-14B never generates.
"""
