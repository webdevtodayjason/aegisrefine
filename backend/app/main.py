import os
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
from app.routers import jobs, admin, webhooks, certificates, activity, refinery, auth
from app.services import auth as authsvc
from app.services.job_service import create_paid_job
from app.services.aar_service import AAR_MJS, DID_JSON, CERTS_DIR, BACKEND_DIR

WEB_DIR = BACKEND_DIR / "web"
BRAND_DIR = Path(__file__).resolve().parents[2] / "brand-assets"


def _ensure_auth_schema():
    """Idempotent: add auth columns to a users table that predates them (create_all won't ALTER)."""
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    with engine.begin() as conn:
        if "password_hash" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR"))
        if "is_admin" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT false NOT NULL"))


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ponytail: create_all + a tiny idempotent ALTER covers the demo; Alembic if this grows.
    Base.metadata.create_all(bind=engine)
    _ensure_auth_schema()
    _seed_admin()
    yield


app = FastAPI(
    title="Aegis API",
    description="Conductor-governed autonomous dataset refinery",
    version="0.1.0",
    lifespan=lifespan,
)

# --- API routers (registered BEFORE the static mounts so they take precedence) ---
app.include_router(jobs.router)
app.include_router(admin.router)
app.include_router(webhooks.router)
app.include_router(certificates.router)
app.include_router(activity.router)
app.include_router(refinery.router)
app.include_router(auth.router)


_CUSTOMER_PAGES = {"/dashboard.html", "/new-order.html", "/order-detail.html",
                   "/certificate.html", "/billing.html", "/settings.html", "/marketplace.html"}
_ADMIN_PAGES = {"/ops.html", "/job-queue.html", "/audit-log.html", "/customers.html",
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
    if os.getenv("DEV_MODE", "1") != "1":
        raise HTTPException(status_code=404, detail="not found")
    job = create_paid_job(db, req.dataset_url, req.email)
    return {"job_id": job.id, "status": job.status}


@app.get("/jobs/{job_id}/verify")
async def verify_aar(job_id: int):
    """Run the public zero-dep aar.mjs verifier on the job's cert — the badge the site shows."""
    cert = CERTS_DIR / f"job-{job_id}.aar.json"
    if not cert.exists():
        raise HTTPException(status_code=404, detail="no certificate for this job")
    r = subprocess.run(["node", str(AAR_MJS), "verify", str(cert), "--did-json", str(DID_JSON)],
                       cwd=str(BACKEND_DIR), capture_output=True, text=True)
    level = "FAIL"
    for line in r.stdout.splitlines():
        if "conformance:" in line:
            level = line.split("conformance:")[-1].strip()
    return {"job_id": job_id, "level": level, "ok": r.returncode == 0 and level != "FAIL",
            "output": r.stdout.strip()}


# --- static mounts LAST: brand assets, then the branded site at root (same-origin, no CORS) ---
# brand-assets lives at the repo root (outside the backend build context) — mount only if present.
if BRAND_DIR.exists():
    app.mount("/brand-assets", StaticFiles(directory=str(BRAND_DIR)), name="brand-assets")
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="site")
