#!/usr/bin/env python3
"""Private Aegis Refine -> Hermes Agent operator bridge.

Run this on the Dell beside Hermes Agent. Bind it to localhost or the Dell's
Tailscale IP, not the public internet.
"""

from __future__ import annotations

import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


HERMES_BIN = os.getenv("HERMES_BIN", "/home/sem/.local/bin/hermes")
SKILL = os.getenv("HERMES_SKILL", "aegis-refine")
TOKEN = os.getenv("HERMES_OPERATOR_TOKEN", "").strip()
MODEL = os.getenv("HERMES_OPERATOR_MODEL", "").strip()
PROVIDER = os.getenv("HERMES_OPERATOR_PROVIDER", "").strip()
RUN_TIMEOUT = int(os.getenv("HERMES_RUN_TIMEOUT_SECONDS", "90"))
SEND_TIMEOUT = int(os.getenv("HERMES_SEND_TIMEOUT_SECONDS", "20"))
TELEGRAM_TARGET = os.getenv("HERMES_TELEGRAM_TARGET", "telegram").strip()


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def _extract_json(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("Hermes did not return a JSON object")
    return data


def _prompt(payload: dict[str, Any]) -> str:
    compact = {
        "job_id": payload.get("job_id"),
        "phase": payload.get("phase"),
        "service": payload.get("service"),
        "status": payload.get("status"),
        "source_kind": (payload.get("source") or {}).get("kind"),
        "quote": payload.get("quote") or {},
        "economics": payload.get("economics") or {},
        "spend_tickets": payload.get("spend_tickets") or [],
        "receipt": payload.get("receipt") or {},
    }
    return (
        "Use aegis-refine. Return compact JSON only. "
        "Schema keys: operator, skill, job_id, service, aegis_health, primary_models, "
        "route, cap, spend_decision, proof, next_action. "
        "Routes: run_local, synthesize, request_spend, temporarily_queue, fail_closed. "
        "No raw data or secrets. Job="
        f"{json.dumps(compact, separators=(',', ':'), sort_keys=True, default=str)}"
    )


def _run_hermes(payload: dict[str, Any]) -> dict[str, Any]:
    cmd = [HERMES_BIN]
    if PROVIDER:
        cmd += ["--provider", PROVIDER]
    if MODEL:
        cmd += ["-m", MODEL]
    cmd += ["--skills", SKILL, "-z", _prompt(payload)]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "Hermes command failed").strip()[:600])
    result = _extract_json(proc.stdout)
    return _normalize_result(payload, result)


def _normalize_result(payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    quote = payload.get("quote") or {}
    out = dict(result)
    out["operator"] = "Hermes Agent"
    out["skill"] = out.get("skill") or SKILL
    out["job_id"] = out.get("job_id") or payload.get("job_id")
    out["service"] = out.get("service") or payload.get("service")
    if not isinstance(out.get("primary_models"), dict):
        out["primary_models"] = {
            "operator": "Hermes Agent",
            "operations_brain": "Nemotron 3 Ultra",
            "data_governance": "Aegis-14B",
        }
    if not isinstance(out.get("cap"), dict):
        out["cap"] = {
            "quoted_usd": quote.get("quoted_usd"),
            "approved_cap_usd": quote.get("approved_cap_usd"),
            "projected_spend_usd": payload.get("economics", {}).get("actual_cost_usd"),
            "cap_respected": True,
        }
    if not isinstance(out.get("spend_decision"), dict):
        out["spend_decision"] = {
            "needed": str(out.get("spend_decision") or "").lower() in {"approve", "approved", "request_spend"},
            "tool_or_model": None,
            "reason": str(out.get("spend_decision") or "Local processing sufficient within cap"),
            "ticket_required": out.get("route") == "request_spend",
        }
    if not isinstance(out.get("proof"), dict):
        out["proof"] = {
            "stripe_verified": bool(quote.get("stripe_checkout_session_id")),
            "quote_receipt_verified": bool(quote.get("receipt")),
            "aar_expected": True,
            "delivery_allowed": payload.get("phase") == "completed",
        }
    out.setdefault("route", "temporarily_queue")
    out.setdefault("next_action", "queue" if out["route"] == "temporarily_queue" else "continue")
    return out


def _queued_result(payload: dict[str, Any], error: Exception) -> dict[str, Any]:
    quote = payload.get("quote") or {}
    return {
        "ok": False,
        "operator": "Hermes Agent",
        "skill": SKILL,
        "job_id": payload.get("job_id"),
        "service": payload.get("service"),
        "aegis_health": "unverified",
        "primary_models": {
            "operator": "Hermes Agent",
            "operations_brain": "Nemotron 3 Ultra",
            "data_governance": "Aegis-14B",
        },
        "route": "temporarily_queue",
        "cap": {
            "quoted_usd": quote.get("quoted_usd"),
            "approved_cap_usd": quote.get("approved_cap_usd"),
            "projected_spend_usd": payload.get("economics", {}).get("actual_cost_usd"),
            "cap_respected": True,
        },
        "spend_decision": {
            "needed": False,
            "tool_or_model": None,
            "reason": "Hermes bridge could not complete the operator pass before the timeout",
            "ticket_required": False,
        },
        "proof": {
            "stripe_verified": bool(quote.get("stripe_checkout_session_id")),
            "quote_receipt_verified": bool(quote.get("receipt")),
            "aar_expected": True,
            "delivery_allowed": False,
        },
        "next_action": "queue",
        "hermes_error": str(error)[:240],
    }


def _receipt_message(payload: dict[str, Any], result: dict[str, Any]) -> str:
    quote = payload.get("quote") or {}
    economics = payload.get("economics") or {}
    receipt = payload.get("receipt") or {}
    return "\n".join([
        "Aegis Refine receipt",
        f"Job: {payload.get('job_id')} ({payload.get('service')})",
        f"Phase: {payload.get('phase')}",
        f"Route: {result.get('route')} / Next: {result.get('next_action')}",
        f"Quote: ${quote.get('quoted_usd')} | Cap: ${quote.get('approved_cap_usd')}",
        f"Revenue: ${economics.get('revenue_collected_usd')} | Cost: ${economics.get('actual_cost_usd')}",
        f"AAR: {receipt.get('aar') or 'pending'}",
        "Operator: Hermes Agent + aegis-refine skill",
    ])


def _send_telegram(payload: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str | None]:
    if payload.get("phase") != "completed" or not TELEGRAM_TARGET:
        return False, None
    proc = subprocess.run(
        [HERMES_BIN, "send", "--to", TELEGRAM_TARGET, _receipt_message(payload, result)],
        capture_output=True,
        text=True,
        timeout=SEND_TIMEOUT,
        check=False,
    )
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "send failed").strip()[:240]
    return True, None


class Handler(BaseHTTPRequestHandler):
    server_version = "AegisHermesOperator/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    def do_GET(self) -> None:
        if self.path != "/health":
            _json_response(self, 404, {"ok": False, "error": "not found"})
            return
        _json_response(self, 200, {"ok": True, "operator": "Hermes Agent", "skill": SKILL})

    def do_POST(self) -> None:
        if self.path != "/operate":
            _json_response(self, 404, {"ok": False, "error": "not found"})
            return
        if TOKEN:
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {TOKEN}":
                _json_response(self, 401, {"ok": False, "error": "unauthorized"})
                return
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 256 * 1024)
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            try:
                result = _run_hermes(payload)
            except Exception as exc:
                result = _queued_result(payload, exc)
            sent, send_error = _send_telegram(payload, result)
            result["telegram_sent"] = sent
            if send_error:
                result["telegram_error"] = send_error
            _json_response(self, 200, result)
        except Exception as exc:
            _json_response(self, 500, {"ok": False, "operator": "Hermes Agent", "error": str(exc)[:600]})


def main() -> None:
    bind = os.getenv("HERMES_OPERATOR_BIND", "127.0.0.1")
    port = int(os.getenv("HERMES_OPERATOR_PORT", "8765"))
    httpd = ThreadingHTTPServer((bind, port), Handler)
    print(f"Aegis Hermes operator bridge listening on {bind}:{port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
