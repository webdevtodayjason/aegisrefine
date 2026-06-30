# Aegis Site Manifest — packet → wired page (single source of truth)

**Rule:** the design packets (`WEB-DESIGN/Competition Platform Design System/site/*.dc.html`) are the **SPEC** (read-only — a proprietary `dc-runtime` React export that cannot be served/wired directly). The **wired site** lives in `backend/web/` and is served by the live FastAPI app. **Exactly one wired page per packet. Never rebuild a page already marked ✅ — convert only what's ⏳/❌.**

| # | Design packet (spec) | Wired page (`backend/web/`) | Persona | Status | Wiring |
|---|---|---|---|---|---|
| 1 | Landing | `index.html` | (marketing) | ✅ | static hero |
| 2 | Pricing | `pricing.html` | (marketing) | ✅ | static |
| 3 | HowItWorks | `how-it-works.html` | (marketing) | ✅ | static |
| 4 | Docs | `docs.html` | (marketing) | ✅ | static |
| 5 | NewOrder | `new-order.html` | REFINE | ✅ | `POST /jobs` checkout + sim-pay |
| 6 | Dashboard | `dashboard.html` | REFINE | ✅ | `GET /jobs`, `/activity` |
| 7 | OrderDetail | `order-detail.html` | REFINE | ✅ | `GET /jobs/{id}`, `POST .../process` |
| 8 | Certificate | `certificate.html` | REFINE | ✅ | `GET .../aar`, `.../verify` |
| 9 | Marketplace | `marketplace.html` | REFINE | ✅ | static catalog |
| 10 | Billing | `billing.html` | REFINE | ✅ | `/activity` ledger + static invoices |
| 11 | Settings | `settings.html` | REFINE | ✅ | UI-only |
| 12 | AdminGate | `ops.html` (Approvals) | OPS | ✅ | `GET /admin/gate/tickets`, approve/reject |
| 13 | JobQueue | `job-queue.html` | OPS | ✅ | `GET /jobs` (all) |
| 14 | AuditLog | `audit-log.html` | OPS | ✅ | `GET /activity` (full) |
| 15 | Customers | `customers.html` | OPS | ✅ | static CRM |
| 16 | Login | `login.html` | (auth) | ❌ | **the auth/account-creation step** |
| — | *(no packet)* | `policies.html`, `agents.html` | OPS | ✅ | designed-to-match |

**Personas:** REFINE = customer app sidebar; OPS = operator/super-admin sidebar (`assets/shell.js` auto-routes by nav key). Marketing pages = standalone top-nav.

**Process:** before building any page, check this table. Build/convert only ⏳/❌ rows. Update the row to ✅ when done.
