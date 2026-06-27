# Aegis — State Audit (Real vs. Faked Inventory)

**Date:** 2026-06-27
**Purpose:** Honest, evidence-based inventory of what is actually built, what returns fake/static data, and what is missing entirely. Intended as the factual basis for a clean engineering handoff before the Hermes hackathon submission (due EOD Tue 6/30).

**Headline:** The product thesis is *"Conductor is the product, not plumbing"* and *"no mock billing, no simulated transactions."* As of this audit, the Conductor layer is 100% fake (static dictionaries), the outbound Stripe spend is a stub, and the backend does not boot. The vision, docs, brand, and UI mockups are strong. The executable core is mostly still ahead.

---

## 1. Boot Status: DOES NOT RUN

`app/models/__init__.py` imports `from .audit_log import AuditLog`, but `app/models/audit_log.py` **does not exist**. Any import of the models package raises `ImportError` on startup. The app cannot start with models loaded until this is fixed.

---

## 2. Real vs. Faked — Backend (`backend/app`)

| File | Status | Notes |
|------|--------|-------|
| `main.py` | REAL (trivial) | Boots root + `/health` + `jobs` router only. **Admin gate router is NOT registered** — approve/reject/execute endpoints are unreachable on the running app. |
| `database.py` | REAL | Standard SQLAlchemy engine/session. No `create_all` and no Alembic migrations present, so a fresh DB has **no tables**. |
| `models/user.py` | REAL | Clean schema. |
| `models/job.py` | REAL | Clean schema. |
| `models/spend_ticket.py` | REAL | Clean schema. **No `approved_by` / `rejected_by` column** — cannot record *who* approved a spend (undercuts the audit-trail claim). |
| `models/audit_log.py` | **MISSING** | Imported but never written. Causes boot failure. |
| `models/audit_certificate.py` | **MISSING** | Specified in ARCHITECTURE.md, never written. |
| `routers/jobs.py` | PARTIALLY REAL | `create_job` makes a **real** Stripe Checkout Session. But: takes `user_id` + `file_path` as raw params (no auth, IDOR, path injection). Creates the Job *before* payment, contradicting the webhook-driven design in ARCHITECTURE.md. |
| `routers/admin.py` | REAL but UNREACHABLE | Real routing into spend_service, but not included in `main.py`. |
| `services/spend_service.py` | MOSTLY REAL + 1 STUB | `create/approve/reject` do real DB state transitions. **`execute_spend_ticket` is a STUB** — flips status to "executed" and never calls Stripe. `approved_by`/`rejected_by` params accepted but never persisted. |
| `conductor/nodes.py` | **100% FAKE** | All 5 nodes (triage, score, propose_spend, human_gate, aar) return hardcoded dictionaries (`file_type: "pdf"`, `12500` tokens, `$2.50`, `complexity: "medium"`). No real processing, no integration, not imported or called anywhere. This is the crown jewel of the pitch and it is currently theater. |
| `tests/` | EMPTY | No tests. |

---

## 3. Real vs. Faked — Frontend (`WEB-DESIGN/.../site`)

16 design-component (`.dc.html`) mockups + `support.js` runtime. **All are visual prototypes with hardcoded data** — fake Stripe payment-intent IDs (`pi_3Q…7xK`), fake audit events, fake amounts, static timelines. **No file calls any real API endpoint** (no `fetch`, no backend wiring). This is normal and expected for design mockups — but nothing in the UI is connected to the backend yet, and the "Stripe" transactions shown on screen are display strings, not real charges.

---

## 4. Missing Entirely (specified in docs, not built)

- **Real Conductor integration** — the existing Frontier Infra Conductor (`@frontier-infra/conductor`). This is the highest-priority gap.
- **Stripe webhook handler** (`POST /webhooks/stripe`) — the architecture says this is what creates the Job and triggers Conductor. Without it, the whole intake flow is wrong.
- **Real Stripe Skills outbound spend** inside `execute_spend_ticket`.
- **Auth router** (`/auth/login`, `/auth/register`) and any auth/authz on the admin gate.
- **AuditLog + AuditCertificate** models and the AAR / signed-certificate (JSON + PDF) generation — the deliverable customers supposedly pay for.
- **DB migrations / table creation.**
- **Frontend ↔ backend wiring.**

---

## 5. Security Flags (real money is involved)

1. **Admin gate has zero authentication.** Anyone who can reach the host can approve and execute real spend. Fix first.
2. **IDOR in `create_job`** — `user_id` is a client-supplied param; you can act as any user.
3. **Path injection** — `file_path` is a raw client string with no upload validation.
4. **No Stripe webhook signature verification** (handler doesn't exist yet, but it's load-bearing).
5. **No idempotency guard** on spend execution beyond the status check.
6. **Audit trail cannot identify the approver** — no `approved_by` persisted.

---

## 6. What IS Genuinely Strong

- Clear, internally consistent positioning and docs (README, MARKETING_BRIEF, ARCHITECTURE, API_MAPPING).
- Complete brand asset set.
- All 16 UI screens designed and visually polished, on-brand.
- Clean data models for User/Job/SpendTicket and a correctly-shaped propose→approve→reject→execute state machine.
- The Stripe Checkout (inbound revenue) path is real code.

---

## 7. Honest Build Completion Estimate

- Vision / docs / brand / UI design: ~90%
- Backend executable core: ~25–30%
- The Conductor layer (the actual thesis): ~0% real
- Real money movement (inbound real / outbound stub): ~50%

**Bottom line for the handoff:** before any demo video is filmed, the real Frontier Infra Conductor must be wired in, `execute_spend_ticket` must call real Stripe Skills, and the boot blockers (missing model, unregistered router, no migrations) must be cleared. Filming the current state would put a fake governance layer and a fake spend on camera — the exact thing the product claims it never does.
