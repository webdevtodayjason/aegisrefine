# Aegis — Backend Architecture

**Project**: aegisrefine.com  
**Goal**: Conductor-governed autonomous dataset refinery with real Stripe earning + gated spending on NVIDIA DGX Spark.

---

## 1. High-Level Architecture

```
Customer (Browser)
    ↓
Marketing Site + App (aegisrefine.com)
    ↓
Conductor Orchestration Layer
    ├── Triage
    ├── Score
    ├── Route
    ├── Propose (spend ticket)
    ├── Human Gate
    └── AAR + Audit Certificate
    ↓
Execution Layer (on Spark 1)
    ├── Local AInode inference (bulk work)
    ├── Stripe Skills (inbound revenue + outbound spend)
    └── External API calls (when approved)
```

**Core Principle**: Conductor is not infrastructure — it is the product. Every meaningful action must pass through it.

---

## 2. Tech Stack (Initial)

| Layer                  | Choice                          | Reason |
|------------------------|----------------------------------|--------|
| **Language**           | Python (FastAPI)                | Best Conductor integration + async + Stripe |
| **Framework**          | FastAPI                         | Modern, fast, great for APIs + webhooks |
| **Database**           | PostgreSQL                      | Reliable, good for audit logs |
| **Job Orchestration**  | Existing Conductor harness      | We already have this |
| **Inference**          | AInode on Spark 1               | Local, fast, private |
| **Payments**           | Stripe (via Stripe Skills)      | Real money in both directions |
| **Deployment**         | Docker on Spark 1 (port 443)    | Direct NVIDIA hardware |
| **Auth**               | JWT + session (or Clerk later)  | Simple start |

---

## 3. Core Data Models (MVP)

### User
- id, email, stripe_customer_id, created_at

### Job
- id, user_id, status, input_file_path, output_file_path
- complexity_score, estimated_cost, actual_cost
- created_at, started_at, completed_at

### SpendTicket
- id, job_id, amount, description, status (proposed / approved / rejected / executed)
- stripe_payment_intent_id (if executed)
- proposed_at, decided_at, executed_at

### AuditLog
- id, job_id, action, actor (system / human), details (JSON), created_at

### AuditCertificate
- id, job_id, pdf_path, json_path, signature, created_at

---

## 4. Critical Flows

### 4.1 Job Creation + Payment
1. User uploads file + pays via Stripe Checkout
2. Webhook creates `Job` record
3. Triggers Conductor `triage` node

### 4.2 Gated Spend Flow (The Demo Moment)
1. Agent hits edge case during processing
2. Creates `SpendTicket` with amount + reason
3. Conductor proposes it to human via dashboard / notification
4. Human approves or rejects
5. If approved → execute via Stripe Skills
6. Record everything in `AuditLog`
7. Continue processing

### 4.3 AAR + Certificate Generation
After job completion:
- Generate After Action Report
- Create signed Audit Certificate (JSON + PDF)
- Store with job
- Make downloadable by customer

---

## 5. Conductor Integration Points

We will treat Conductor as the central brain. Key integration points:

- **Intake** → Conductor triage node
- **Complexity scoring** → Conductor score node
- **Spend proposal** → Conductor propose node + human gate
- **Execution routing** → Conductor decides local vs external
- **AAR generation** → Conductor AAR node

---

## 6. Security & Trust Considerations

- All spend actions require explicit human approval (no auto-execute above threshold)
- Every action is logged immutably
- Audit certificates are signed and exportable
- Local inference preferred for data residency
- Stripe keys and sensitive config stored securely

---

## 7. Phased Implementation Plan

### Phase 0 (Today)
- Architecture doc
- Folder structure
- Basic FastAPI skeleton

### Phase 1 (Day 1)
- User + Job models
- Stripe webhook for job creation
- Basic Conductor intake

### Phase 2 (Day 2)
- SpendTicket + Human Gate flow
- Local AInode integration stub
- Audit logging

### Phase 3 (Day 3)
- AAR + Audit Certificate generation
- Polish + demo prep

---

## 8. Open Decisions

- Use existing Conductor instance or fork a lightweight version for this project?
- How will the Human Gate UI be exposed? (Separate admin dashboard vs embedded in customer view?)
- Will we use the premium AInode tier on Spark 1 for gated spend, or a real external API?

---

**Next**: Confirm the stack and open decisions, then start Phase 0 scaffolding.