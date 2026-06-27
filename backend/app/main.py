import os
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app import models  # noqa: F401 — import so Base.metadata sees every table
from app.routers import jobs, admin, webhooks, certificates, activity, refinery
from app.services.job_service import create_paid_job
from app.services.aar_service import AAR_MJS, DID_JSON, CERTS_DIR, BACKEND_DIR

WEB_DIR = BACKEND_DIR / "web"
BRAND_DIR = Path(__file__).resolve().parents[2] / "brand-assets"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ponytail: create_all is fine for the demo; swap to Alembic for prod migrations.
    Base.metadata.create_all(bind=engine)
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
