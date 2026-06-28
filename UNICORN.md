# Aegis — The Unicorn

> **An autonomous agent that runs a profitable data-refinery business: it quotes the job,
> earns the capped price, spends its own budget on the cheapest compute that does a good job,
> delivers a clean dataset, and hands you a receipt you can verify.**

## The one-liner
*Got data? Give it to us — any format. An agent prices it up front (a flat cap, no surprise
bills), turns it into a clean, PII-safe training/RAG dataset on private NVIDIA hardware, and
signs a certificate you can independently re-verify. It only reaches for paid compute when the
data demands it — and never without staying under the price it quoted you.*

## Why it's the unicorn — the economic loop
The product isn't "a data cleaner." It's **an agent running a real business with a P&L**:

1. **QUOTE** — Aegis-14B (our Hermes-4 fine-tune, live on a DGX Spark) evaluates the dataset
   and prices it from {size, complexity, data type, expected models/tools}. One flat number.
2. **EARN** — customer accepts the quote → Stripe charges the **capped** amount. Real revenue.
3. **BUDGET** — the accepted quote is a **hard spend cap** with a target margin. Acceptance
   pre-authorizes the agent to spend up to the cap, autonomously.
4. **SPEND (cost-optimized)** — the agent does the bulk work free + locally; for hard chunks it
   picks the **cheapest-good-enough** provider/model (internal OCR → Z.ai/GLM vision / OpenAI /
   NVIDIA Nemotron) to protect its margin. Real metered token/tool spend. A spend that would
   blow the cap arms a human gate (re-quote / approve overrun).
5. **RUN REAL OPS** — a deterministic engine actually produces the clean dataset (the model
   *judges*, it never *writes* the data).
6. **PROVE** — a signed Ed25519 certificate records `quoted_usd / spent_usd / margin_usd` plus
   data guarantees, and the public verifier **re-runs** the checks (PII=0, deduped, schema-valid,
   input→output lineage). Proof, not paper.

## Why the judges care (Hermes × NVIDIA × Stripe: "earn, spend, run real operations")
This is the rare entry that does **all three for real, as one loop**:
- **EARN** — real Stripe revenue, priced by the agent.
- **SPEND** — the agent controls its own COGS: chooses model / effort / provider to stay
  profitable. Genuine agency over money, not a scripted call.
- **RUN REAL OPS** — it ships a real, usable dataset.
- **Hermes** — Aegis-14B *is* a Hermes-4-14B fine-tune, and it's the pricer + governor.
- **NVIDIA** — local-first on DGX Spark; paid escalation to hosted Nemotron only when justified.
- **Stripe** — money in (Checkout) and money out (the agent pays for the services it uses).
It reads as **a fully automated company**: quotes, gets paid, manages cost, books margin, proves
its work.

## The moat (honest)
The cleaning itself is commodity. The defensible value is the **trust + economics layer**:
- **Capped quote** = no surprise bills (the #1 fear of an autonomous agent with a card).
- **Re-verifiable PII-safety** = "provably safe to put in production / RAG" (the #1 fear of
  feeding internal data to AI).
- **A signed P&L per job** = an agent you can audit.
We don't have to be radically different. We have to be **the easiest, safest, provable** way to
turn any data into a usable dataset — run by an agent that pays its own way.

## The agent's game — self-play, a P&L leaderboard, and a profit/quality benchmark
The economic loop isn't just run — it's **scored**, and the agent plays to win:

- **The bet (per job):** the agent sets a flat **quote** for the customer, privately **estimates its
  own cost**, and picks a **target margin %**. It does *not* reveal the cost — it commits to the
  quote and lives with the outcome.
- **The score (tracked on the backend):** `quoted_usd`, `est_cost_usd` (its private guess),
  `actual_cost_usd` (real metered spend), `target_margin_pct`, `realized_margin_usd`, **outcome**
  (win / thin / **loss** — yes, it can lose money), and `estimate_error` (was its guess right?).
- **The leaderboard:** win rate, avg realized-vs-target margin, **cost-estimate accuracy**, cumulative
  P&L, and the **trend** — is it getting *better* over time? That trend is the proof of learning.
- **The profit/quality frontier (the benchmark):** run real datasets across margin targets (20→80%)
  and measure **profit AND quality together** — quality = the re-verifiable guarantees (PII=0, dedup,
  schema-valid) + Aegis-14B's own quality score + yield (rows_out/rows_in). The question Jason posed:
  *how profitable can it be and still produce good data?* We answer it with **real numbers, run many
  times before the video**, and set the default margin at the frontier.
- **The flywheel (the killer narrative):** every game it plays is itself a labeled record
  (job features → quote → actual outcome). That log **is a dataset** — so we refine it *with our own
  product* and fine-tune Aegis-14B on its own play. The agent gets better at running its business by
  training on itself. We dogfood the refinery to improve the refinery.

Why the judges care: this is **measurable economic agency + self-improvement** — not "an agent that
spent money once," but one with **audited books, a win/loss record, and a benchmark proving it's good
at the business.** Exactly the usefulness/viability bar NVIDIA × Stripe × Nous set.

## Who it's for
Teams fine-tuning or building RAG who must **trust and prove** their data: regulated/enterprise
AI (legal, health, finance), anyone facing an AI/data audit, anyone who can't ship data to a
cloud, anyone burned by runaway agent costs.

## Honest status (2026-06-27)
Live + real: Stripe earn, Aegis-14B governance on the Spark, human-gated spend *decision*, signed
certs, auth, deploy. **Being built to this contract:** the quote engine, the real curation engine
(today the cert signs client-supplied bytes), the verifier re-running its checks, and one real
paid escalation. See `CURATION_PLAN.md` and the locked contract. Hard rule throughout: **no fake
data, spend, proof, or quote.**
