from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.job import Job
from app.services import refinery

router = APIRouter(prefix="/jobs", tags=["refinery"])


class ProcessRequest(BaseModel):
    sample: str
    hard_doc: str | None = None


class CompleteRequest(BaseModel):
    output: str


def _get_job(db: Session, job_id: int) -> Job:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/{job_id}/process")
async def process(job_id: int, req: ProcessRequest, db: Session = Depends(get_db)):
    """Run Aegis-14B governance over the job; arms the human gate if it proposes a spend."""
    job = _get_job(db, job_id)
    return refinery.process_job(db, job, req.sample, req.hard_doc)


@router.post("/{job_id}/complete")
async def complete(job_id: int, req: CompleteRequest, db: Session = Depends(get_db)):
    """Finish the job and issue its signed AAR certificate over the real output."""
    job = _get_job(db, job_id)
    signed = refinery.complete_job(db, job, req.output.encode("utf-8"))
    return {"job_id": job_id, "aar": f"/jobs/{job_id}/aar", "conformance_target": "L2", "sig": signed["sig"]}
