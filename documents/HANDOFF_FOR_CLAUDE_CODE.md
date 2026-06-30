# Aegis Backend — Handoff for Claude Code (Verified)

**Project:** Aegis (aegisrefine.com)
**Date:** 2026-06-27
**Recipient:** Claude Code
**Author note:** Every claim below is cross-checked against the actual repo. Anything not verifiable from the repo is marked **[UNVERIFIED]** or **[FABRICATED]** — do not treat those as fact, and do not invent replacements. When a value is unknown, leave it blank and ask Jason.

---

## 0. READ FIRST — The app does not currently boot

`backend/app/models/__init__.py` imports `from .audit_log import AuditLog`, but `backend/app/models/audit_log.py` **does not exist**. Importing the models package raises `ImportError`. Running `uvicorn app.main:app` will crash immediately. Fix this before anything else: either create the `AuditLog` model or remove the import.

There are also **no tables created** — no Alembic migrations exist and `Base.metadata.create_all` is never called. A fresh database has no schema.

---

## 1. Mission (unchanged, non-negotiable)

"Conductor is the product, not plumbing." Every demo path must be real: real Stripe earning, real human-gated spending via Stripe Skills, real audit trails + signed certificates, real execution on NVIDIA hardware (Spark 1 + AInode), real orchestration via Jason's existing Conductor. **No fake data, no stubbed decisions, no simulated money.**

---

## 2. REAL vs. NOT — verified against the repo

| Component | Status | Evidence / Note |
|-----------|--------|-----------------|
| `database.py` SQLAlchemy setup | ✅ REAL | Standard engine/session/`get_db`. No pooling config. |
| `models/user.py`, `job.py`, `spend_ticket.py` | ✅ REAL | Clean schemas. No relationships defined. No `approved_by` column on SpendTicket. |
| `models/audit_log.py` | ❌ MISSING | Imported in `__init__.py`; file absent → boot crash. |
| `models/audit_certificate.py` | ❌ MISSING | In ARCHITECTURE.md; never written. |
| `routers/jobs.py` → Stripe Checkout (inbound) | ✅ REAL | Genuinely creates a `stripe.checkout.Session`. This is the one real money path. |
| `routers/jobs.py` auth/inputs | ⚠️ INSECURE | Takes `user_id` + `file_path` as raw params (IDOR + path injection). Creates Job before payment, contradicting webhook-driven design. |
| `routers/admin.py` gate endpoints | ⚠️ REAL BUT UNREACHABLE | Logic is real; router is **not registered** in `main.py` (only `jobs.router` is). Endpoints don't exist on the running app. |
| `services/spend_service.py` create/approve/reject | ✅ REAL | Real DB state transitions. `approved_by`/`rejected_by` params accepted but **never persisted**. |
| `services/spend_service.py` `execute_spend_ticket` | ❌ STUB | Flips status to "executed"; **never calls Stripe**. Comment: `# TODO: Call real Stripe Skills here`. The "real gated spend" is currently fake. |
| `conductor/nodes.py` (all 5 nodes) | ❌ FAKE | Pure functions returning hardcoded dicts (`"pdf"`, `12500`, `$2.50`). **Zero network calls.** Not imported or invoked anywhere. |
| Frontend `WEB-DESIGN/.../site/*.dc.html` (16 screens) | 🎨 MOCKUP ONLY | Polished, on-brand, but all data is hardcoded (fake `pi_...` IDs, fake events). No `fetch`, no backend wiring. Expected for design mockups — just not connected. |
| `tests/` | ❌ EMPTY | No tests. |
| Stripe webhook handler | ❌ MISSING | `STRIPE_WEBHOOK_SECRET` is in `.env.example` but no handler exists. |
| Auth (`/auth/login`, `/auth/register`) | ❌ MISSING | In API_MAPPING.md; not built. |
| AAR / certificate generation | ❌ MISSING | Not built. |

---

## 3. Security holes to close (real money is involved)

1. **Admin gate has no auth** — anyone reaching the host can approve/execute real spend. Fix first.
2. **IDOR in `create_job`** — client supplies `user_id`; act as anyone.
3. **Path injection** — `file_path` is a raw client string, no upload validation.
4. **No Stripe webhook signature verification** (handler doesn't exist yet, but it's load-bearing).
5. **No idempotency guard** on spend execution beyond the status check.
6. **No approver identity recorded** — no `approved_by` column, so the audit trail can't prove *who* approved a spend. This undercuts the core product claim; add it.

---

## 4. Conductor integration — FILL FROM SOURCE OF TRUTH, DO NOT INVENT

**What the repo actually contains:** one line — `CONDUCTOR_API_URL=http://localhost:8001` in `backend/.env.example`. That is the *only* Conductor fact in the codebase.

**[FABRICATED — ignore from the prior handoff]:** `https://conductor.frontier-infra.com`, `http://conductor.internal:8001`, and the endpoint paths `/triage`, `/score`, `/propose`, `/human-gate`, `/aar`. These were not read from any real source; the URL has been confirmed fake by Jason. Do **not** build against them.

**What is real (per Jason, not the repo):** Jason has a real Conductor running on his network, reachable over a real Tailscale network alongside Spark 1. The integration is real and intended — but the exact base URL, auth scheme, and endpoint contract must come from the actual Conductor service (its code or its docs), supplied by Jason.

**Action for Claude Code:** Before writing the Conductor client, ask Jason for (or read from the real Conductor source):
- exact base URL / host reachable over Tailscale
- auth scheme (header name + token format)
- the real request/response contract for each orchestration step

Leave these blank until provided. Replace the fake dicts in `conductor/nodes.py` with calls to the verified contract — and nothing before then.

```
CONDUCTOR_BASE_URL = ___________   # from Jason
CONDUCTOR_AUTH     = ___________   # from Jason
# endpoints/contract: ___________  # from real Conductor source
```

---

## 5. Things in the prior handoff to disregard

- **§17 "USE_MOCK_CONDUCTOR" toggle** — do not add a mock-Conductor mode that "simulates successful spend proposals." It reintroduces the exact failure this project is fighting. Mock only inside isolated unit tests, never as a runtime/demo path.
- **§9 invented Conductor URLs/endpoints labeled "confirmed structure"** — fabricated (see §4).
- **§4 env block** — malformed (section headers merged into values). The real env vars are: `DATABASE_URL`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `CONDUCTOR_API_URL`, `AINODE_API_URL`, `SECRET_KEY`. `RESEND_API_KEY` is **not** in the repo (it's a planned key Jason still owes).
- **Generic boilerplate sections** (DB backups, API versioning, Celery concurrency, structlog config) — fine as someday-ideas, but not relevant to the 3-day submission; don't let them set priority.

---

## 6. Recommended order (3-day scope)

**Phase 1 — make it boot and be safe**
1. Fix the missing `audit_log.py` (create model or remove import).
2. Register `admin.router` in `main.py`.
3. Add admin auth (simple `X-Admin-Key` against env is acceptable for the window).
4. Fix `create_job`: derive `user_id` from auth, accept a real upload (`UploadFile`) or validated URL.
5. Add Alembic migrations (or `create_all` on startup for the demo).

**Phase 2 — real money + real orchestration (the thesis)**
6. Stripe webhook handler with signature verification; payment success creates/advances the Job.
7. Implement real `execute_spend_ticket` via Stripe Skills; add idempotency + persist `approved_by`.
8. Wire the job lifecycle through Jason's **real** Conductor (per §4). Conductor proposes → SpendTicket created → job pauses at human gate → approve → execute → resume.

**Phase 3 — deliverable + polish**
9. AuditLog + AuditCertificate models; AAR generation; signed certificate (JSON + PDF). HMAC-SHA256 signing is a reasonable choice.
10. Connect the existing UI mockups to the live endpoints.
11. Seed a clean demo dataset; rehearse the live card swipe + gate approval.

---

## 7. Design principles (must hold)

1. Conductor must be visibly real in the demo.
2. No spend executes without an explicit, recorded human approval (with approver identity).
3. The signed audit certificate is the primary deliverable.
4. All money movement is real Stripe — inbound and outbound.

---

**End — verified handoff. When in doubt, leave it blank and ask Jason. Do not fill gaps with plausible guesses.**
