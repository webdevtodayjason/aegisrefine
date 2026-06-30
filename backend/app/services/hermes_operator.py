"""Hermes Agent operator bridge.

The web app never shells out directly or exposes a terminal. It sends a bounded job
payload to a private Hermes bridge on the same trusted network, then stores Hermes'
operator receipt on the audit trail.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.job import Job
from app.models.spend_ticket import SpendTicket
from app.services.audit import log_action


OPERATOR_ACTIONS = (
    "hermes_operator_decision",
    "hermes_operator_unavailable",
)


def configured() -> bool:
    return bool((os.getenv("HERMES_OPERATOR_URL") or "").strip())


def _source_kind(source: str | None, service: str | None) -> str:
    if service == "synthesis":
        return "seed_or_reference"
    s = source or ""
    if s.startswith("users/") and "/uploads/" in s:
        return "uploaded_file"
    if s.startswith("http://") or s.startswith("https://"):
        return "url"
    if s.startswith("/"):
        return "local_upload_handle"
    return "unknown"


def _redact_source(source: str | None) -> str | None:
    if not source:
        return None
    if source.startswith("users/") and "/uploads/" in source:
        return "uploaded_file"
    if source.startswith("/"):
        return "local_upload_handle"
    return source[:240]


def _job_payload(db: Session, job: Job, phase: str, receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    tickets = (
        db.query(SpendTicket)
        .filter(SpendTicket.job_id == job.id)
        .order_by(SpendTicket.id)
        .all()
    )
    return {
        "job_id": job.id,
        "phase": phase,
        "service": getattr(job, "service", "refine"),
        "status": job.status,
        "source": {
            "kind": _source_kind(job.input_file_path, getattr(job, "service", "refine")),
            "value": _redact_source(job.input_file_path),
        },
        "quote": {
            "quoted_usd": job.quote_amount,
            "approved_cap_usd": job.approved_cap,
            "target_margin_pct": job.target_margin_pct,
            "receipt": job.quote_breakdown or {},
            "stripe_checkout_session_id": job.stripe_checkout_session_id,
        },
        "economics": {
            "revenue_collected_usd": job.revenue_collected,
            "actual_cost_usd": job.actual_cost,
        },
        "synthesis": {
            "topic": getattr(job, "synth_topic", None),
            "target_kept": getattr(job, "synth_target_kept", None),
            "reference_kind": _source_kind(getattr(job, "synth_reference", None), "refine"),
        },
        "spend_tickets": [
            {
                "id": t.id,
                "status": t.status,
                "amount": t.amount,
                "actual_amount": t.actual_amount,
                "provider": t.provider,
                "kind": t.kind,
                "cost_source": t.cost_source,
                "description": t.description,
            }
            for t in tickets
        ],
        "receipt": receipt or {},
    }


def _post_json(url: str, payload: dict[str, Any], timeout: float, token: str | None) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(256 * 1024).decode("utf-8", "replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Hermes bridge returned a non-object payload")
    return data


def dispatch_job(
    db: Session,
    job: Job,
    *,
    phase: str,
    receipt: dict[str, Any] | None = None,
    require_config: bool = False,
) -> dict[str, Any]:
    """Dispatch one job phase to Hermes Agent and persist the receipt.

    Automatic pipeline calls set `require_config=False` so a missing bridge never blocks
    delivery during local tests. Manual/admin calls set it true and surface configuration
    problems honestly.
    """
    url = (os.getenv("HERMES_OPERATOR_URL") or "").strip()
    if not url:
        if require_config:
            raise HTTPException(status_code=503, detail="Hermes operator bridge is not configured")
        return {"ok": False, "status": "unconfigured"}
    payload = _job_payload(db, job, phase, receipt)
    timeout = float(os.getenv("HERMES_OPERATOR_TIMEOUT_SECONDS", "120"))
    token = (os.getenv("HERMES_OPERATOR_TOKEN") or "").strip() or None
    try:
        result = _post_json(url, payload, timeout, token)
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as e:
        details = {"phase": phase, "error": str(e)[:240]}
        log_action(db, job.id, "hermes_operator_unavailable", "hermes", details)
        if require_config:
            raise HTTPException(status_code=503, detail="Hermes operator bridge is unavailable")
        return {"ok": False, "status": "unavailable", **details}

    details = {
        "phase": phase,
        "operator": result.get("operator") or "Hermes Agent",
        "skill": result.get("skill") or "aegis-refine",
        "route": result.get("route"),
        "next_action": result.get("next_action"),
        "telegram_sent": result.get("telegram_sent"),
        "result": result,
    }
    log_action(db, job.id, "hermes_operator_decision", "hermes", details)
    return details


def latest_operator_payload(db: Session, job_id: int) -> dict[str, Any] | None:
    row = (
        db.query(AuditLog)
        .filter(AuditLog.job_id == job_id, AuditLog.action.in_(OPERATOR_ACTIONS))
        .order_by(AuditLog.id.desc())
        .first()
    )
    if not row:
        return None
    return {
        "action": row.action,
        "actor": row.actor,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "details": row.details or {},
    }
