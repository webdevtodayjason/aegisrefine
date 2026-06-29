import os
import asyncio
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from sqlalchemy import inspect, text
from app.database import Base, engine, get_db, SessionLocal
from app.models.user import User
from app import models  # noqa: F401 — import so Base.metadata sees every table
from fastapi.responses import RedirectResponse
from app.routers import jobs, admin, webhooks, certificates, activity, refinery, auth, scoreboard, downloads, health
from app.services import auth as authsvc
from app.services.job_service import create_paid_job
from app.services.aar_service import AAR_MJS, DID_JSON, CERTS_DIR, BACKEND_DIR

WEB_DIR = BACKEND_DIR / "web"
BRAND_DIR = Path(__file__).resolve().parents[2] / "brand-assets"


_REQUIRED_COLUMNS = {
    "users": [("password_hash", "VARCHAR"), ("is_admin", "BOOLEAN DEFAULT false NOT NULL")],
    "jobs": [("stripe_checkout_session_id", "VARCHAR"),
             ("quote_amount", "DOUBLE PRECISION"), ("approved_cap", "DOUBLE PRECISION"),
             ("quote_status", "VARCHAR DEFAULT 'draft'"), ("quote_breakdown", "JSONB"),
             ("target_margin_pct", "DOUBLE PRECISION DEFAULT 0.65"),
             ("margin_floor_pct", "DOUBLE PRECISION DEFAULT 0.55"),
             ("revenue_collected", "DOUBLE PRECISION"),
             ("requires_human_quote", "BOOLEAN DEFAULT false"),
             ("quote_accepted_at", "TIMESTAMPTZ"),
             ("service", "VARCHAR DEFAULT 'refine'"), ("synth_topic", "VARCHAR"),
             ("synth_target_kept", "INTEGER"), ("synth_reference", "VARCHAR"),
             ("output_data", "TEXT")],
    "spend_tickets": [("kind", "VARCHAR DEFAULT 'gated'"), ("gate_reason", "VARCHAR"),
                      ("provider", "VARCHAR"), ("units", "DOUBLE PRECISION"),
                      ("unit_price_usd", "DOUBLE PRECISION"), ("cost_source", "VARCHAR"),
                      ("actual_amount", "DOUBLE PRECISION")],
    "audit_certificates": [("content", "TEXT")],
}


def _ensure_columns():
    """Idempotent: add columns to tables that predate them (create_all won't ALTER existing tables).
    pg-typed DDL only runs on the live Postgres; fresh sqlite already has them via create_all."""
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, cols in _REQUIRED_COLUMNS.items():
            if table not in tables:
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols:
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def _seed_admin():
    """Seed/promote the admin from ADMIN_EMAIL / ADMIN_PASSWORD env (bootstrap only)."""
    email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
    pw = os.getenv("ADMIN_PASSWORD") or ""
    if not email or not pw:
        return
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        if not u:
            db.add(User(email=email, password_hash=authsvc.hash_password(pw), is_admin=True))
            db.commit()
        elif not u.is_admin:
            u.is_admin = True
            db.commit()
    finally:
        db.close()


def _sweep_orphaned():
    """A redeploy kills in-flight background tasks, leaving jobs stuck 'processing'. Any job still
    'processing' at boot was run by the now-dead old container -> mark it failed (no silent zombies)."""
    db = SessionLocal()
    try:
        from app.models.job import Job
        stuck = db.query(Job).filter(Job.status == "processing").all()
        for j in stuck:
            j.status = "failed"
        if stuck:
            db.commit()
    except Exception:
        pass
    finally:
        db.close()


async def _queued_retry_loop():
    """Best-effort in-process retry worker for jobs parked while Aegis-14B was busy."""
    interval = float(os.getenv("AEGIS_QUEUE_POLL_SECONDS", "30"))
    if interval <= 0:
        return
    from app.services.job_runner import run_due_jobs

    while True:
        await asyncio.sleep(interval)
        db = SessionLocal()
        try:
            run_due_jobs(db, limit=int(os.getenv("AEGIS_QUEUE_BATCH", "5")))
        except Exception:
            pass
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ponytail: create_all + a tiny idempotent ALTER covers the demo; Alembic if this grows.
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    _seed_admin()
    _sweep_orphaned()
    retry_task = asyncio.create_task(_queued_retry_loop())
    try:
        yield
    finally:
        retry_task.cancel()
        try:
            await retry_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Aegis API",
    description="Conductor-governed autonomous dataset refinery",
    version="0.1.0",
    lifespan=lifespan,
)

# --- API routers (registered BEFORE the static mounts so they take precedence) ---
app.include_router(jobs.router)
app.include_router(admin.router)
app.include_router(admin.receipts_router)
app.include_router(webhooks.router)
app.include_router(certificates.router)
app.include_router(downloads.router)
app.include_router(activity.router)
app.include_router(refinery.router)
app.include_router(auth.router)
app.include_router(scoreboard.router)
app.include_router(health.router)


# new-order.html is intentionally PUBLIC — a logged-out visitor can build a quote; auth is
# collected in-flow (the wizard prompts account creation when /jobs/quote returns 401).
_CUSTOMER_PAGES = {"/dashboard.html", "/order-detail.html",
                   "/certificate.html", "/billing.html", "/settings.html", "/marketplace.html"}
_ADMIN_PAGES = {"/ops.html", "/job-queue.html", "/job-receipt.html", "/audit-log.html", "/customers.html",
                "/policies.html", "/agents.html"}


@app.middleware("http")
async def guard_pages(request, call_next):
    """Server-side gate for page HTML: customer pages need a session; admin pages need is_admin."""
    path = request.url.path
    protected = path in _CUSTOMER_PAGES or path in _ADMIN_PAGES
    if protected:
        tok = request.cookies.get(authsvc.COOKIE)
        payload = authsvc.read_token(tok) if tok else None
        if not payload:
            return RedirectResponse(url="/login.html", status_code=302)
        if path in _ADMIN_PAGES and not payload.get("adm"):
            return RedirectResponse(url="/dashboard.html", status_code=302)
    resp = await call_next(request)
    if protected:
        # never let a browser cache an authed page shell (else a logged-out user still sees it)
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/health")
async def health():
    return {"status": "healthy"}


class SimulatedPayment(BaseModel):
    dataset_url: str
    email: str


@app.post("/dev/simulate-payment")
async def simulate_payment(req: SimulatedPayment, db: Session = Depends(get_db)):
    """DEV ONLY — create a paid Job without a real Stripe round-trip, for demo rehearsal.
    Disabled unless DEV_MODE=1. The authentic path stays Stripe Checkout + the webhook."""
    if os.getenv("DEV_MODE", "0") != "1":
        raise HTTPException(status_code=404, detail="not found")
    job = create_paid_job(db, req.dataset_url, req.email)
    return {"job_id": job.id, "status": job.status}


@app.get("/jobs/{job_id}/verify")
async def verify_aar(job_id: int, db: Session = Depends(get_db)):
    """Verify the job's cert: (1) the Ed25519 signature + L2 via the public aar.mjs verifier,
    AND (2) RE-RUN the data guarantees on the delivered file (PII=0 / dedup / schema). The
    second part is what makes the certificate a guarantee you can check, not a claim."""
    import tempfile
    from app.models.audit_certificate import AuditCertificate as _AC
    from app.models.job import Job as _Job
    from app.curate import engine as _ce
    _tmp = []
    cert_row = db.query(_AC).filter(_AC.job_id == job_id).order_by(_AC.id.desc()).first()
    cert_path = None
    if cert_row and cert_row.content:                # DB copy survives redeploys
        tf = tempfile.NamedTemporaryFile("w", suffix=".aar.json", delete=False)
        tf.write(cert_row.content); tf.close(); cert_path = tf.name; _tmp.append(cert_path)
    elif (CERTS_DIR / f"job-{job_id}.aar.json").exists():
        cert_path = str(CERTS_DIR / f"job-{job_id}.aar.json")
    if not cert_path:
        raise HTTPException(status_code=404, detail="no certificate for this job")
    r = subprocess.run(["node", str(AAR_MJS), "verify", cert_path, "--did-json", str(DID_JSON)],
                       cwd=str(BACKEND_DIR), capture_output=True, text=True)
    level = "FAIL"
    for line in r.stdout.splitlines():
        if "conformance:" in line:
            level = line.split("conformance:")[-1].strip()
    resp = {"job_id": job_id, "level": level, "ok": r.returncode == 0 and level != "FAIL",
            "output": r.stdout.strip()}
    job = db.query(_Job).filter(_Job.id == job_id).first()
    ds_path = None
    if job and job.output_data:                      # re-run guarantees on the in-DB dataset
        df = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        df.write(job.output_data); df.close(); ds_path = df.name; _tmp.append(ds_path)
    elif job and job.output_file_path and os.path.exists(job.output_file_path):
        ds_path = job.output_file_path
    if ds_path:
        resp["guarantees_recheck"] = _ce.verify_output(ds_path)
    for p in _tmp:
        try:
            os.unlink(p)
        except OSError:
            pass
    return resp


# --- static mounts LAST: brand assets, then the branded site at root (same-origin, no CORS) ---
# brand-assets lives at the repo root (outside the backend build context) — mount only if present.
if BRAND_DIR.exists():
    app.mount("/brand-assets", StaticFiles(directory=str(BRAND_DIR)), name="brand-assets")
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="site")
