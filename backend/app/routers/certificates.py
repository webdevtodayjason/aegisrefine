import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pathlib import Path
from app.database import get_db
from app.models.audit_certificate import AuditCertificate
from app.services.aar_service import DID_JSON

router = APIRouter(tags=["certificates"])


@router.get("/jobs/{job_id}/aar")
async def get_job_aar(job_id: int, db: Session = Depends(get_db)):
    """The public proof surface: serve the signed AAR certificate for a job."""
    cert = (
        db.query(AuditCertificate)
        .filter(AuditCertificate.job_id == job_id)
        .order_by(AuditCertificate.id.desc())
        .first()
    )
    if not cert or not Path(cert.json_path).exists():
        raise HTTPException(status_code=404, detail="no certificate for this job")
    return JSONResponse(content=json.loads(Path(cert.json_path).read_text()))


@router.get("/.well-known/did.json")
async def did_document():
    """did:web resolution — lets anyone verify our AAR signatures by public key."""
    if not DID_JSON.exists():
        raise HTTPException(status_code=404, detail="did.json not generated")
    return JSONResponse(content=json.loads(DID_JSON.read_text()))
