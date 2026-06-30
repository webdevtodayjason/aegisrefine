# Aegis — Session Handoff (next Claude Code session)

**Project:** Aegis (aegisrefine.com) · **Updated:** 2026-06-27 · **Status:** mid-flight (NOT closing out)
**This supersedes** the old `HANDOFF.md` (by "Hermes", which contained fabricated Conductor URLs) and folds in `HANDOFF_FOR_CLAUDE_CODE.md`. Full vault: `/Users/sem/Obsidian Vault/Aegis/`.

> ⚠️ Anti-fakery is the prime directive. A prior agent fabricated Conductor endpoints; the entire
> project (and the AAR brand) dies if the demo is faked. **No fake data, no stubbed decisions, no
> simulated money.** When a fact isn't verifiable, leave it blank and ask Jason.

## Compaction handoff
- **Branch:** none — repo is `git init`'d but has **zero commits**. All work is uncommitted in the working tree. *Recommended first action next session: baseline commit (ask Jason first).*
- **Last decision:** the agent IS Aegis-14B — it makes the judgment (pick spend/model), Conductor does the deterministic math + enforces the one human gate. Maps to The Machine.
- **Next step:** EARN (Stripe `checkout.session.completed` webhook → kills the IDOR) + PROVE (vendor `aar.mjs`, keygen `did:web`, signed cert) + public audit-feed endpoint.
- **Open questions:** see bottom.

## What this is
Entry in the **Hermes Agent Accelerated Business Hackathon** (NVIDIA × Stripe × Nous). **Due EOD Tue 2026-06-30.** Deliverable = 1–3 min demo video (tweet @NousResearch) + writeup + Typeform (`form.typeform.com/to/hpEifIK4`). Judged on usefulness / viability / presentation by the three sponsors. Real goal: get Jason's **Frontier Infra** stack (Conductor, AVL, AAR, The Machine) + **AInode** in front of those judges. Aegis = an autonomous dataset-refinery business built on them.

## Verified REAL vs NOT (cross-checked against source, 2026-06-27)
| Thing | State |
|---|---|
| Backend boots | ✅ FIXED this session (was ImportError on missing `audit_log.py`) |
| `database.py`, User/Job/SpendTicket/AuditLog/AuditCertificate models | ✅ real, tables build |
| Human gate (`admin.py`) registered + `X-Admin-Key` auth | ✅ done this session (was unreachable + unauthed) |
| `spend_service` records `approved_by` + writes audit trail | ✅ done this session |
| Aegis-14B client (`app/services/agent.py`) | ✅ built + self-checked offline |
| Inbound Stripe Checkout (`jobs.py`) | ⚠️ real session, but creates Job pre-payment + client-supplied `user_id` (IDOR). **Fix in EARN.** |
| Stripe webhook handler | ❌ not built (EARN) |
| `execute_spend_ticket` real outbound spend | ❌ stub — TODO Stripe Link CLI (Phase 2) |
| Real Conductor wiring | ❌ not wired (fake `conductor/nodes.py` DELETED this session) |
| AAR signed certificate | ❌ not built (PROVE) |
| AVL companion / public audit feed | ❌ not built (rides on AuditLog) |
| 16 UI screens (`WEB-DESIGN/.../site/*.dc.html`) | 🎨 mockups, hardcoded data, no backend wiring |

## The architecture (the loop)
1. Stripe-paid job → Aegis creates a Conductor item (`ItemVault.create_item`).
2. **Conductor (deterministic, token-free):** `TriageEngine.dedup/score/route` grades the dataset.
3. **Aegis maps routes → costed vendor/model options** (small price map).
4. **Aegis-14B decides** (judgment + rationale) — `decide("spend", ...)` → strict JSON.
5. Arm gate: `ItemVault.set_status(slug,'awaiting_approval')`; human sees ONE yes/no w/ rationale + rejected alternatives.
6. Approve → `proposal_actions.py approve <slug>` → agent runs **Stripe Link CLI** spend (non-zero exit = no money). Deny → `shelve`.
7. Aegis-14B `audit` job output → **AAR cert payload** → signed → public verifier green on camera (+ tamper→FAIL).

`triage`/`quality`/`spend`/`audit` are the model's four jobs (see `MODEL_INTEGRATION.md`). `spend` IS the gate card; `audit` IS the cert payload.

## Demo spine (90s) — camera cut = AVL + AAR + Conductor + AInode/Aegis-14B
EARN (Stripe Checkout) → RUN (Aegis-14B on a DGX Spark via AInode, `GET /v1/models`) → GATE (agent's costed choice, human approves) → SPEND (Stripe Link CLI) → PROVE (signed AAR, verifier green + 1-byte tamper FAIL). The Machine / ADL / NemoClaw / argentos / titanium = writeup credits only.

## Repo state / how to run
- Backend at `backend/`. venv at `backend/.venv` (gitignored). `openai` added to `requirements.txt`.
- Boot smoke test (sqlite, no external creds): `/private/tmp/claude-501/.../scratchpad/smoke_phase1a.py` — passes (boot, schema, gate registered, money-path audit, approver persisted, gate auth).
- Agent client self-check: `.venv/bin/python app/services/agent.py`.
- Env: `backend/.env.example` — `ADMIN_API_KEY`, `AINODE_API_URL=http://10.100.0.14:8001/v1`, `AINODE_MODEL=Aegis-14B`, `AINODE_API_KEY=EMPTY`. Conductor is **in-process** (no HTTP) — `CONDUCTOR_REPO_PATH` / `HERMES_KANBAN_DB`.

## Authoritative companion docs
- `MODEL_INTEGRATION.md` — Aegis-14B endpoint, the verbatim system prompt (self-name `Aegis-7B`!), 4 job schemas. **Jason owns; living doc.**
- `CONDUCTOR_CONTRACT.md` — the VERIFIED in-process Conductor contract (ItemVault / TriageEngine / proposal_actions.py). No HTTP.
- `HANDOFF_FOR_CLAUDE_CODE.md` — Jason's corrected handoff (still valid).
- Vault `/Users/sem/Obsidian Vault/Aegis/` — full project state.

## Open questions / blockers (need Jason)
1. **Conductor:** path to your real `frontier-infra/conductor` checkout (`CONDUCTOR_REPO_PATH`) + is a Hermes Kanban board DB already created on the Spark? (Full multi-agent board needs running Hermes; single gate is demo-real without it.)
2. **Outbound spend:** live Stripe Link CLI (real phone approval) vs Issuing test-mode for the on-camera money move?
3. **System prompt:** stays `Aegis-7B` until you retrain — you said you'd send info on the 14B flip.
4. **Baseline commit:** ok to make the first git commit?
