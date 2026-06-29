"""Signed download PACKAGE + a PUBLIC certificate-verification endpoint.

GET /jobs/{id}/package  — owner-scoped .zip bundling the produced dataset, its signed
AAR certificate, and a VERIFY.txt that tells anyone holding the bundle how to confirm it.

POST /verify  — PUBLIC, no auth. Anyone with a downloaded certificate.aar.json can confirm
it is genuine + ours (Ed25519, did:web:aegisrefine.com) by re-running the SAME vendored
verifier the owner-only /jobs/{id}/verify uses. This is what makes the certificate a proof
a third party can check, not a claim only the owner can see.

ponytail: stdlib zipfile/io for the bundle; stdlib email parser for multipart so we add NO
new runtime dep (python-multipart is intentionally not installed — see auth.py).
"""
import io
import json
import os
import subprocess
import tempfile
import zipfile
from email.parser import BytesParser
from email.policy import default as _EMAIL_POLICY

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.audit_certificate import AuditCertificate
from app.models.job import Job
from app.models.user import User
from app.services import storage
from app.services.aar_service import AAR_MJS, CERTS_DIR, DID_JSON, BACKEND_DIR
from app.services.auth import require_user

router = APIRouter(tags=["downloads"])


def _dataset_bytes(job: Job) -> bytes | None:
    """Resolve the produced dataset for a job from its durable homes, in order:
    in-DB blob -> R2 key -> local fs path. None if the job has no output yet."""
    if job.output_data:                                  # DB copy survives redeploys
        data = job.output_data.encode("utf-8")
        return data if data.strip() else None
    src = job.output_file_path
    if src:
        if src.startswith("users/") and storage.enabled():   # R2 key (shared contract)
            try:
                return storage.get_bytes(src)
            except Exception:
                return None
        if os.path.exists(src):                          # local fs path
            with open(src, "rb") as f:
                data = f.read()
                return data if data.strip() else None
    return None


def _cert_text(db: Session, job_id: int) -> str | None:
    """The signed AAR JSON text for a job — DB copy first (survives redeploys), then on-disk cert."""
    cert = (db.query(AuditCertificate).filter(AuditCertificate.job_id == job_id)
            .order_by(AuditCertificate.id.desc()).first())
    if cert and cert.content:
        return cert.content
    if cert and cert.json_path and os.path.exists(cert.json_path):
        with open(cert.json_path) as f:
            return f.read()
    p = CERTS_DIR / f"job-{job_id}.aar.json"
    if p.exists():
        return p.read_text()
    return None


def _verify_txt(job_id: int, recorded_sha256: str | None) -> str:
    """Plain-text instructions bundled in the package so anyone can re-verify offline or online."""
    sha_line = (f"   recorded in this certificate: {recorded_sha256}\n"
                if recorded_sha256 else "")
    return (
        "AEGIS DATASET PACKAGE — how to verify\n"
        "=====================================\n\n"
        f"This bundle is the deliverable for Aegis job #{job_id}. It contains:\n"
        "  - dataset.jsonl         the produced dataset (one JSON record per line)\n"
        "  - certificate.aar.json  an Ed25519-signed Agent Attestation Record (AAR)\n"
        "  - VERIFY.txt            this file\n\n"
        "WHAT THE CERTIFICATE PROVES\n"
        "  The certificate is signed with Ed25519 by Aegis (did:web:aegisrefine.com).\n"
        "  Inside it, checks[0].response_sha256 is the SHA-256 of the dataset, encoded as\n"
        "  unpadded base64url. That binds this exact dataset to this signed certificate.\n"
        f"{sha_line}\n"
        "1) CONFIRM THE CERTIFICATE IS GENUINE + OURS (online, no login)\n"
        "   POST certificate.aar.json to https://aegisrefine.com/verify\n"
        "     curl -F file=@certificate.aar.json https://aegisrefine.com/verify\n"
        "   A genuine cert returns {\"ok\": true, \"level\": \"L2\", \"signer\": \"did:web:aegisrefine.com\"}.\n\n"
        "2) CONFIRM IT OFFLINE WITH OUR PUBLIC KEY\n"
        "   Our public key is published at https://aegisrefine.com/.well-known/did.json\n"
        "   Verify with the open AAR tool:\n"
        "     node aar.mjs verify certificate.aar.json --did-json did.json\n\n"
        "3) CONFIRM THE DATASET MATCHES THE CERTIFICATE\n"
        "   Recompute the dataset hash and compare to checks[0].response_sha256:\n"
        "     openssl dgst -sha256 -binary dataset.jsonl | basenc --base64url | tr -d '='\n"
        "   (or in Python: base64.urlsafe_b64encode(hashlib.sha256(open('dataset.jsonl','rb')\n"
        "   .read()).digest()).rstrip(b'=') )\n"
    )


@router.get("/jobs/{job_id}/package")
async def download_package(job_id: int, db: Session = Depends(get_db),
                           user: User = Depends(require_user)):
    """Owner-scoped signed proof bundle (.zip): dataset.jsonl + certificate.aar.json + VERIFY.txt."""
    j = db.query(Job).filter(Job.id == job_id).first()
    if j and not user.is_admin and j.user_id != user.id:
        raise HTTPException(status_code=404, detail="no dataset output yet")
    data = _dataset_bytes(j) if j else None
    if data is None:
        raise HTTPException(status_code=404, detail="no dataset output yet")

    cert = _cert_text(db, job_id)
    recorded_sha = None
    if cert:
        try:
            recorded_sha = json.loads(cert)["checks"][0]["response_sha256"]
        except Exception:
            recorded_sha = None

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("dataset.jsonl", data)
        if cert:
            zf.writestr("certificate.aar.json", cert)
        zf.writestr("VERIFY.txt", _verify_txt(job_id, recorded_sha))
    headers = {"Content-Disposition": f'attachment; filename="aegis-dataset-{job_id}.zip"'}
    return Response(content=buf.getvalue(), media_type="application/zip", headers=headers)


def _extract_cert_text(content_type: str, raw: bytes) -> str | None:
    """Pull the certificate JSON text from EITHER a multipart upload OR a raw JSON body.
    Multipart is parsed with the stdlib email parser so we don't pull in python-multipart."""
    if "multipart/form-data" in (content_type or "").lower():
        msg = BytesParser(policy=_EMAIL_POLICY).parsebytes(
            b"Content-Type: " + (content_type or "").encode() + b"\r\n\r\n" + raw)
        if msg.is_multipart():
            for part in msg.iter_parts():
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", "replace")
        return None
    return raw.decode("utf-8", "replace") if raw else None


@router.post("/verify")
async def verify_certificate(request: Request):
    """PUBLIC — verify any downloaded certificate.aar.json. Runs the SAME vendored verifier as
    /jobs/{id}/verify (Ed25519 sig + L0/L1/L2) against our published did.json. No auth: anyone
    holding a package can confirm the cert is genuine + ours. Accepts multipart file OR JSON body."""
    raw = await request.body()
    cert_text = _extract_cert_text(request.headers.get("content-type", ""), raw)
    if not cert_text or not cert_text.strip():
        raise HTTPException(status_code=400,
                            detail="provide a certificate.aar.json (multipart 'file' or JSON body)")
    try:
        cert = json.loads(cert_text)
    except Exception:
        raise HTTPException(status_code=400, detail="not valid JSON — expected a certificate.aar.json")

    tf = tempfile.NamedTemporaryFile("w", suffix=".aar.json", delete=False)
    try:
        tf.write(cert_text)
        tf.close()
        r = subprocess.run(
            ["node", str(AAR_MJS), "verify", tf.name, "--did-json", str(DID_JSON)],
            cwd=str(BACKEND_DIR), capture_output=True, text=True)
    finally:
        try:
            os.unlink(tf.name)
        except OSError:
            pass

    level = "FAIL"
    for line in r.stdout.splitlines():
        if "conformance:" in line:
            level = line.split("conformance:")[-1].strip()
    signer = (cert.get("sig") or {}).get("by") or cert.get("principal") or cert.get("subject")
    return JSONResponse(content={
        "ok": r.returncode == 0 and level != "FAIL",
        "level": level,
        "signer": signer,
        "output": (r.stdout + r.stderr).strip(),
    })
