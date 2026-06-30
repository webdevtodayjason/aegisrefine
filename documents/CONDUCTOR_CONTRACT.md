# Conductor Contract — VERIFIED from source (frontier-infra/conductor)

> Recon cloned the real repo and grepped it twice. **Conductor has NO HTTP surface** —
> no base URL, no auth header, no per-step request/response. `requirements.txt` is PyYAML
> only; zero hits for fastapi/flask/uvicorn/httpx/requests/webhook/bearer. The old
> `CONDUCTOR_API_URL=http://localhost:8001` was a **fabrication trap** (a prior agent
> invented `/triage /score /propose` endpoints from it). It's been removed from `.env.example`.
> The real contract is **in-process Python + CLI + SQLite**:

## 1. State — ItemVault (`engine/item_vault.py`)
One markdown file per item at `vault/items/<slug>.md` with YAML frontmatter.
- `create_item()` seeds `status='triage'`
- `set_status(slug, 'awaiting_approval')` **arms the human gate**

## 2. Deterministic steps — TriageEngine (`engine/engine.py`)
`dedup / score / score_heuristic / route / research_specs / prep_specs / fulfillment_specs`
→ return `TaskSpec` dataclasses (`title/body/role/parents/workspace_kind/workspace_path`).
Token-free, no LLM. Materialize via `KanbanStore.create_task(conn, title=, body=, ...)`
→ `'t_'+8hex` into a Hermes Kanban SQLite DB (`~/.hermes/kanban/boards/<board>/kanban.db`;
`HERMES_KANBAN_DB` overrides; **DB must already exist** or `connect()` raises).

## 3. The gate — `proposal_actions.py`
`subprocess proposal_actions.py approve|shelve|shelve-all|modify <slug> [--change/--reason]`
(cwd=repo, env `TRIAGE_CONFIG / TRIAGE_VAULT_DIR / HERMES_KANBAN_DB`).
- **Refuses** unless frontmatter `status == 'awaiting_approval'`
- Emits ONE JSON object on stdout; approve → `{ok:true, next_task_id, next_assignee, chain:[...]}`
- Exit codes: 1 = bad input, 2 = bad state, 3 = backend error

## How Aegis integrates
Aegis is the HTTP layer. Expose **our own** `/jobs` and `/jobs/{slug}/approve` that wrap the
vault + subprocess + SQLite ops above. There is nothing to authenticate *through* to Conductor —
provide our own authn/authz (the `X-Admin-Key` gate). Conductor's only security model is the one
human gate + scope rails. The Hermes/Aegis-14B agent runs as a decision node: Conductor scores/routes
→ Aegis maps to costed vendor/model options → **Aegis-14B picks + gives rationale** → status flips to
`awaiting_approval` → human yes/no → on approve, run the Stripe Link CLI spend.

## Still needs Jason (the only real unknowns)
- [ ] Path to your real `frontier-infra/conductor` checkout → `CONDUCTOR_REPO_PATH`
- [ ] Is a Hermes Kanban board DB already created on the Spark? (`HERMES_KANBAN_DB`) — the full
      multi-agent board needs a running Hermes install; the **single human gate is demo-real without it**.

## Outbound spend (Stripe Skills) — VERIFIED
`@stripe/link-cli` v0.8.2 (real on npm, @stripe.com maintainers). Agent shells:
`link-cli spend-request create --payment-method-id <pm> --merchant-name --merchant-url --context --amount <cents> --request-approval`
→ `--request-approval` pushes to the operator's Link app and **blocks**; `returncode 0` = approved →
spend; non-zero = denied/timeout = **do not spend**. PAN via `--output-file` (never to stdout/logs).
Fallback for the window: Stripe **Issuing** test-mode virtual card + `issuing_authorization.request` webhook.
