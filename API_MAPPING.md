# Aegis — Page to Backend Endpoint Mapping

This document maps every HTML mockup to the required backend routes, data, and Conductor integration points.

---

## 1. Marketing / Public Pages

| HTML File              | Purpose                          | Required Backend Endpoints                          | Notes |
|------------------------|----------------------------------|-----------------------------------------------------|-------|
| `Landing.dc.html`      | Hero + value prop                | None (static)                                       | — |
| `HowItWorks.dc.html`   | Conductor flow explanation       | None (static)                                       | — |
| `Pricing.dc.html`      | Pricing tiers                    | None (static)                                       | — |
| `Docs.dc.html`         | Documentation + audit examples   | `GET /docs/audit-sample` (future)                   | — |
| `Login.dc.html`        | Login / Sign up                  | `POST /auth/login`, `POST /auth/register`           | JWT or session |

---

## 2. Customer Dashboard Pages

| HTML File                  | Purpose                                      | Required Backend Endpoints                                      | Data Models Involved          | Conductor Nodes |
|---------------------------|----------------------------------------------|------------------------------------------------------------------|-------------------------------|-----------------|
| `Dashboard.dc.html`       | Overview of jobs + status                    | `GET /jobs`, `GET /jobs/{id}`                                   | Job, User                     | — |
| `NewOrder.dc.html`        | Upload file + create job                     | `POST /jobs` (with file upload + Stripe checkout)               | Job, User                     | triage, score |
| `OrderDetail.dc.html`     | Live job status + deliverables               | `GET /jobs/{id}`, `GET /jobs/{id}/certificate`                  | Job, AuditCertificate         | aar |
| `Certificate.dc.html`     | View / download signed audit certificate     | `GET /certificates/{id}`                                        | AuditCertificate              | aar |
| `Billing.dc.html`         | Invoices + payment history                   | `GET /billing/invoices`                                         | User, Job                     | — |
| `Settings.dc.html`        | Account settings                             | `GET /account`, `PATCH /account`                                | User                          | — |
| `Marketplace.dc.html`     | Curated dataset library (future)             | `GET /marketplace/datasets`                                     | —                             | — |

---

## 3. Admin / Ops Dashboard Pages (Internal)

| HTML File                | Purpose                                           | Required Backend Endpoints                                      | Data Models Involved          | Conductor Nodes          | Notes |
|--------------------------|---------------------------------------------------|------------------------------------------------------------------|-------------------------------|--------------------------|-------|
| `AdminGate.dc.html`      | Human Gate — approve/reject spend proposals       | `GET /admin/gate/tickets`, `POST /admin/gate/{id}/approve`, `POST /admin/gate/{id}/reject` | SpendTicket, Job              | human_gate               | Highest priority |
| `JobQueue.dc.html`       | All customer jobs + status                        | `GET /admin/jobs`                                               | Job                           | —                        | — |
| `AuditLog.dc.html`       | System-wide audit trail                           | `GET /admin/audit-logs`                                         | AuditLog                      | —                        | — |
| `Customers.dc.html`      | Customer list + overview                          | `GET /admin/customers`                                          | User, Job                     | —                        | — |

---

## 4. Key Backend Endpoints Summary (MVP Priority)

### Public / Auth
- `POST /auth/login`
- `POST /auth/register`

### Customer
- `POST /jobs` — Create job + trigger Stripe checkout
- `GET /jobs` — List user's jobs
- `GET /jobs/{id}` — Job detail + status
- `GET /jobs/{id}/certificate` — Download audit certificate

### Admin / Human Gate (Critical)
- `GET /admin/gate/tickets` — List pending spend proposals
- `POST /admin/gate/{id}/approve`
- `POST /admin/gate/{id}/reject`
- `POST /admin/gate/{id}/execute` (after approval)

### Internal / System
- `POST /webhooks/stripe` — Stripe webhook handler
- `POST /internal/conductor/triage`
- `POST /internal/conductor/score`
- `POST /internal/conductor/propose-spend`
- `POST /internal/conductor/aar`

---

## 5. Conductor Integration Points

| Flow Step          | Conductor Node     | Triggered By                     | Output |
|--------------------|--------------------|----------------------------------|--------|
| Job intake         | triage             | `POST /jobs`                     | Metadata + complexity estimate |
| Scoring            | score              | After triage                     | Risk + cost score |
| Spend proposal     | propose            | During processing                | SpendTicket |
| Human decision     | human_gate         | Admin dashboard                  | Approved / Rejected |
| Final report       | aar                | Job completion                   | AuditCertificate |

---

**This mapping now gives full visibility into what the backend must support to match the existing HTML mockups.**