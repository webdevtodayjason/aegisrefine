from starlette.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.audit_log import AuditLog
from app.models.job import Job
from app.models.user import User


def _client(email):
    c = TestClient(app, follow_redirects=False)
    r = c.post("/auth/signup", json={"email": email, "password": "hunter2pass"})
    assert r.status_code == 200, r.text
    return c


def _user_id(email):
    db = SessionLocal()
    try:
        return db.query(User).filter(User.email == email).one().id
    finally:
        db.close()


def _job_with_log(user_id, status, action, details):
    db = SessionLocal()
    try:
        job = Job(user_id=user_id, status=status, input_file_path="/tmp/input.jsonl")
        db.add(job)
        db.commit()
        db.refresh(job)
        db.add(AuditLog(job_id=job.id, action=action, actor="system", details=details))
        db.commit()
        return job.id
    finally:
        db.close()


def test_failed_job_detail_surfaces_latest_safe_failure_reason():
    email = "failure-detail@test.com"
    c = _client(email)
    job_id = _job_with_log(
        _user_id(email),
        "failed",
        "curation_error",
        {"error": "source needs OCR before curation", "path": "/tmp/private.pdf"},
    )

    r = c.get(f"/jobs/{job_id}")

    assert r.status_code == 200, r.text
    out = r.json()
    assert out["failure_code"] == "ocr_required"
    assert out["failure_reason"] == "OCR required before curation can continue."
    assert "private" not in str(out)


def test_list_jobs_surfaces_temporarily_queued_reason():
    email = "failure-list@test.com"
    c = _client(email)
    job_id = _job_with_log(
        _user_id(email),
        "queued",
        "aegis_temporarily_queued",
        {"stage": "triage", "error": "AINODE unreachable"},
    )

    r = c.get("/jobs/")

    assert r.status_code == 200, r.text
    job = next(j for j in r.json() if j["id"] == job_id)
    assert job["failure_code"] == "aegis_temporarily_queued"
    assert job["failure_reason"] == "Temporarily queued for Aegis-14B governance."
    assert "AINODE unreachable" not in str(job)


def test_failure_reason_classes_cover_job_failure_modes():
    cases = [
        ("no-usable", "curation_error", {"error": "no usable records produced"},
         "no_usable_records", "No usable training records were found."),
        ("curation", "curation_error", {"error": "parser raised at /tmp/private/source.csv"},
         "curation_error", "Curation failed while preparing this dataset."),
        ("synth-zero", "synthesis_failed", {"reason": "no synthetic rows kept", "candidates": 0},
         "synthesis_zero_kept_rows", "Synthesis finished with zero kept rows."),
    ]

    for suffix, action, details, code, reason in cases:
        email = f"failure-{suffix}@test.com"
        c = _client(email)
        job_id = _job_with_log(_user_id(email), "failed", action, details)

        r = c.get(f"/jobs/{job_id}")

        assert r.status_code == 200, r.text
        out = r.json()
        assert out["failure_code"] == code
        assert out["failure_reason"] == reason
        assert "private" not in str(out)
