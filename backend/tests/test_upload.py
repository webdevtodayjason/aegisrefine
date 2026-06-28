"""File-upload path: POST /jobs/upload -> handle, /jobs/quote accepts a handle (no URL validation),
the handle rides the signed token into job.input_file_path, and completed outputs land in R2.
These exercise ONLY the wiring owned here; quote_service/engine reading R2 bytes is their own slice."""
import json
import os

from starlette.testclient import TestClient

from app.main import app
from app.routers import jobs as jobs_router
from app.services import quote_service, storage, refinery, agent
from app.services.job_service import is_upload_handle, create_paid_job
from app.models.job import Job


def _authed_client(email):
    c = TestClient(app, follow_redirects=False)
    r = c.post("/auth/signup", json={"email": email, "password": "hunter2pass"})
    assert r.status_code == 200, r.text
    return c


# --- unit: handle detection ---

def test_is_upload_handle():
    assert is_upload_handle("users/7/uploads/abc-data.jsonl")          # R2 key
    assert is_upload_handle("/tmp/aegis-upload-xy-data.jsonl")          # local temp path
    assert not is_upload_handle("https://example.com/data.jsonl")      # an https URL is NOT a handle
    assert not is_upload_handle("")


# --- POST /jobs/upload (dev fallback: storage disabled -> local temp handle) ---

def test_upload_dev_fallback_writes_temp_handle():
    # storage disabled (conftest default) -> the handle is a real local temp path holding the bytes
    c = _authed_client("upload-a@test.com")
    body = b'{"prompt":"hi","completion":"ok"}\n'
    r = c.post("/jobs/upload", files={"file": ("data.jsonl", body, "application/x-ndjson")})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["filename"] == "data.jsonl" and out["size"] == len(body)
    assert out["content_type"] == "application/x-ndjson"
    handle = out["handle"]
    assert is_upload_handle(handle)
    assert open(handle, "rb").read() == body          # dev handle is a real temp path with the bytes


def test_upload_r2_branch_returns_key_and_stores(monkeypatch):
    # storage enabled -> the handle is an R2 key and the bytes go to put_bytes (no real network here)
    seen = {}
    monkeypatch.setattr(storage, "enabled", lambda: True)   # overrides the conftest default-off
    monkeypatch.setattr(storage, "put_bytes",
                        lambda key, data, content_type="application/octet-stream":
                        seen.update(key=key, data=data, ct=content_type))
    c = _authed_client("upload-r2@test.com")
    body = b'{"prompt":"q","completion":"a"}\n'
    r = c.post("/jobs/upload", files={"file": ("d.jsonl", body, "application/x-ndjson")})
    assert r.status_code == 200, r.text
    handle = r.json()["handle"]
    assert handle.startswith("users/") and is_upload_handle(handle)
    assert seen["key"] == handle and seen["data"] == body and seen["ct"] == "application/x-ndjson"


def test_upload_rejects_too_large(monkeypatch):
    monkeypatch.setattr(jobs_router, "MAX_UPLOAD_BYTES", 4)   # shrink the cap so the test is cheap
    c = _authed_client("upload-big@test.com")
    r = c.post("/jobs/upload", files={"file": ("big.jsonl", b"0123456789", "application/x-ndjson")})
    assert r.status_code == 413


def test_upload_requires_auth():
    c = TestClient(app, follow_redirects=False)
    r = c.post("/jobs/upload", files={"file": ("data.jsonl", b"x", "application/x-ndjson")})
    assert r.status_code == 401


# --- /jobs/quote routes a handle to quote_service WITHOUT https validation ---

def test_quote_uses_upload_handle_without_url_validation(monkeypatch):
    captured = {}

    def fake_quote_job(source, email, now):
        captured["source"] = source
        return {"quoted_usd": 55.0, "cap_usd": 55.0, "n_records": 3, "data_type": "jsonl",
                "complexity": 0.3, "complexity_scored_by": "heuristic", "target_margin_pct": 65.0,
                "requires_human_quote": False, "token": "tok.sig"}

    monkeypatch.setattr(quote_service, "quote_job", fake_quote_job)
    c = _authed_client("quote-h@test.com")
    handle = "users/9/uploads/deadbeef-data.jsonl"     # an R2 key: would FAIL validate_https_url
    r = c.post("/jobs/quote", json={"upload_handle": handle})
    assert r.status_code == 200, r.text
    assert captured["source"] == handle                # the handle reached quote_job verbatim
    assert r.json()["token"] == "tok.sig"


def test_quote_requires_a_source():
    c = _authed_client("quote-none@test.com")
    assert c.post("/jobs/quote", json={}).status_code == 400


def test_quote_still_validates_a_bare_url():
    c = _authed_client("quote-url@test.com")
    r = c.post("/jobs/quote", json={"dataset_url": "ftp://nope/data"})   # not https -> rejected
    assert r.status_code == 400


# --- the handle rides into job.input_file_path on paid-job creation ---

def test_create_paid_job_carries_upload_handle(db, user):
    handle = f"users/{user.id}/uploads/abc123-data.jsonl"
    job = create_paid_job(db, handle, user.email, quote_amount=55.0)
    assert job.input_file_path == handle


# --- completed outputs are pushed to R2 (best-effort) without breaking the DB-blob fallback ---

def test_complete_job_pushes_outputs_to_r2(db, user, tmp_path, write_jsonl, monkeypatch):
    monkeypatch.setattr(agent, "decide", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    puts = []
    monkeypatch.setattr(storage, "enabled", lambda: True)
    monkeypatch.setattr(storage, "put_bytes",
                        lambda key, data, content_type="application/octet-stream": puts.append((key, len(data))))

    src = write_jsonl(tmp_path, [{"prompt": "hi a@b.com", "completion": "ok"},
                                 {"question": "x", "answer": "y"}])
    job = Job(user_id=user.id, status="processing", input_file_path=src, quote_amount=100.0,
              approved_cap=100.0, revenue_collected=100.0, target_margin_pct=0.65)
    db.add(job); db.commit(); db.refresh(job)

    refinery.process_job(db, job, sample="s")
    cert = refinery.complete_job(db, job)

    keys = [k for k, _ in puts]
    assert keys == [storage.job_key(job.user_id, job.id, "dataset.jsonl"),
                    storage.job_key(job.user_id, job.id, "certificate.aar.json")]
    assert job.output_data                                  # DB-blob fallback still written
    assert cert["guarantees"]["pii_residual"] == 0


def test_complete_job_survives_r2_hiccup(db, user, tmp_path, write_jsonl, monkeypatch):
    monkeypatch.setattr(agent, "decide", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(storage, "enabled", lambda: True)

    def boom(*a, **k):
        raise RuntimeError("R2 unreachable")
    monkeypatch.setattr(storage, "put_bytes", boom)

    src = write_jsonl(tmp_path, [{"prompt": "q", "completion": "a"}, {"question": "x", "answer": "y"}])
    job = Job(user_id=user.id, status="processing", input_file_path=src, quote_amount=100.0,
              approved_cap=100.0, revenue_collected=100.0, target_margin_pct=0.65)
    db.add(job); db.commit(); db.refresh(job)
    refinery.process_job(db, job, sample="s")
    cert = refinery.complete_job(db, job)            # R2 throws -> job still completes + signs
    assert job.status == "completed" and cert["guarantees"]["schema_valid"] is True
