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
RUNTIME_MODE = os.getenv("HERMES_OPERATOR_RUNTIME", os.getenv("HERMES_OPERATOR_MODE", "local")).strip().lower()
NEMOCLAW_BIN = os.getenv("NEMOCLAW_BIN", "nemohermes").strip()
NEMOCLAW_SANDBOX = os.getenv("NEMOCLAW_SANDBOX", "aegis-hermes").strip()
NEMOCLAW_HERMES_BIN = os.getenv("NEMOCLAW_HERMES_BIN", "hermes").strip()
NEMOCLAW_INFERENCE_MODEL = os.getenv("NEMOCLAW_INFERENCE_MODEL", "").strip()
OPENSHELL_BIN = os.getenv("OPENSHELL_BIN", "openshell").strip()
PROVIDER = os.getenv("HERMES_OPERATOR_PROVIDER", "").strip()
MODEL = os.getenv("HERMES_OPERATOR_MODEL", "").strip()
FALLBACK_MODEL = os.getenv("HERMES_OPERATOR_FALLBACK_MODEL", "").strip()
OPERATIONS_MODEL = os.getenv("HERMES_OPERATIONS_MODEL", "nvidia/nemotron-3-ultra-550b-a55b").strip()
CONTENT_SAFETY_MODEL = os.getenv("HERMES_CONTENT_SAFETY_MODEL", "nvidia/nemotron-3.5-content-safety").strip()
STRIPE_VENDOR_ACCOUNT = os.getenv("STRIPE_AGENT_SPEND_VENDOR_ACCOUNT", "").strip()
MAX_AGENT_SPEND_CENTS = int(os.getenv("MAX_AGENT_SPEND_CENTS", "5000"))
RUN_TIMEOUT = int(os.getenv("HERMES_RUN_TIMEOUT_SECONDS", "90"))
PRIMARY_TIMEOUT = int(os.getenv("HERMES_OPERATOR_PRIMARY_TIMEOUT_SECONDS", str(RUN_TIMEOUT)))
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
    spend_instruction = ""
    if payload.get("phase") == "spend_approved":
        spend_instruction = (
            " Phase spend_approved: initiate outbound spend as a Stripe Connect Transfer to the "
            f"AINode vendor account {STRIPE_VENDOR_ACCOUNT or '[configured vendor env missing]'}. "
            f"Hard circuit breaker MAX_AGENT_SPEND_CENTS={MAX_AGENT_SPEND_CENTS}. "
            "Use the aegis-refine Stripe transfer helper or an available Stripe tool/skill. "
            "Return spend.executed.stripe_transfer_id only if Stripe returned a real tr_ id. "
            "Set spend.verified_against_stripe=false because the Aegis backend verifies it independently. "
            "If no transfer is created, return spend.executed=null, route=temporarily_queue, next_action=queue."
        )
    return (
        "Use aegis-refine. Return compact JSON only. "
        "Schema keys: operator, skill, job_id, service, aegis_health, primary_models, safety_gate, "
        "route, cap, spend_decision, spend, proof, next_action. "
        "Routes: run_local, synthesize, request_spend, temporarily_queue, fail_closed. "
        f"Operations primary={OPERATIONS_MODEL}. Content safety gate={CONTENT_SAFETY_MODEL}. "
        "If no raw dataset sample is present, safety_gate.status must be metadata_only or pending. "
        "No raw data or secrets."
        f"{spend_instruction} Job="
        f"{json.dumps(compact, separators=(',', ':'), sort_keys=True, default=str)}"
    )


def _model_roles(active_model: str | None, fallback_used: bool = False) -> dict[str, Any]:
    active = active_model or MODEL or "Hermes configured default"
    if RUNTIME_MODE in {"nemoclaw", "nemohermes", "openshell"} and not active_model:
        active = NEMOCLAW_INFERENCE_MODEL or "NemoClaw inference.local configured model"
    return {
        "operator": "Hermes Agent",
        "operations_brain": {
            "primary": OPERATIONS_MODEL,
            "active": active,
            "fallback": FALLBACK_MODEL or None,
            "fallback_used": fallback_used,
        },
        "content_safety_gate": CONTENT_SAFETY_MODEL,
        "data_governance": "Aegis-14B",
    }


def _brief_error(error: Exception) -> str:
    if isinstance(error, subprocess.TimeoutExpired):
        return "Hermes model attempt timed out"
    text = str(error)
    if "No LLM provider configured" in text:
        return "Hermes provider is not configured for this model"
    if "timed out" in text.lower():
        return "Hermes model attempt timed out"
    return "Hermes model attempt failed"


def _runtime_label() -> str:
    if RUNTIME_MODE in {"nemoclaw", "nemohermes"}:
        return "NemoClaw / nemohermes"
    if RUNTIME_MODE == "openshell":
        return "NemoClaw / OpenShell"
    return "local"


def _runtime_metadata(status: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "mode": RUNTIME_MODE or "local",
        "runtime": _runtime_label(),
        "status": status,
    }
    if RUNTIME_MODE in {"nemoclaw", "nemohermes", "openshell"}:
        metadata["sandbox"] = NEMOCLAW_SANDBOX
        if NEMOCLAW_INFERENCE_MODEL:
            metadata["inference_model"] = NEMOCLAW_INFERENCE_MODEL
    return metadata


def _is_sandbox_runtime() -> bool:
    return RUNTIME_MODE in {"nemoclaw", "nemohermes", "openshell"}


def _hermes_cmd(payload: dict[str, Any], model: str | None, hermes_bin: str | None = None) -> list[str]:
    cmd = [hermes_bin or HERMES_BIN]
    if PROVIDER:
        cmd += ["--provider", PROVIDER]
    if model:
        cmd += ["-m", model]
    cmd += ["--skills", SKILL, "-z", _prompt(payload)]
    return cmd


def _operator_cmd(payload: dict[str, Any], model: str | None) -> list[str]:
    if RUNTIME_MODE in {"", "local"}:
        return _hermes_cmd(payload, model, HERMES_BIN)
    if RUNTIME_MODE in {"nemoclaw", "nemohermes"}:
        if not NEMOCLAW_SANDBOX:
            raise RuntimeError("NEMOCLAW_SANDBOX is required for NemoClaw runtime")
        cmd = _hermes_cmd(payload, model, NEMOCLAW_HERMES_BIN)
        return [NEMOCLAW_BIN, NEMOCLAW_SANDBOX, "exec", "--", *cmd]
    if RUNTIME_MODE == "openshell":
        if not NEMOCLAW_SANDBOX:
            raise RuntimeError("NEMOCLAW_SANDBOX is required for OpenShell runtime")
        cmd = _hermes_cmd(payload, model, NEMOCLAW_HERMES_BIN)
        return [OPENSHELL_BIN, "sandbox", "exec", "-n", NEMOCLAW_SANDBOX, "--", *cmd]
    raise RuntimeError(f"Unsupported HERMES_OPERATOR_RUNTIME={RUNTIME_MODE!r}")


def _run_hermes_once(payload: dict[str, Any], model: str | None, timeout: int) -> dict[str, Any]:
    cmd = _operator_cmd(payload, model)
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "Hermes command failed").strip()[:600])
    return _extract_json(proc.stdout)


def _run_hermes(payload: dict[str, Any]) -> dict[str, Any]:
    attempts: list[tuple[str | None, int, bool]] = []
    attempts.append((MODEL or None, PRIMARY_TIMEOUT, False))
    if FALLBACK_MODEL and FALLBACK_MODEL != MODEL:
        attempts.append((FALLBACK_MODEL, RUN_TIMEOUT, True))

    last_error: Exception | None = None
    for model, timeout, fallback_used in attempts:
        try:
            result = _run_hermes_once(payload, model, timeout)
            out = _normalize_result(payload, result, active_model=model, fallback_used=fallback_used)
            if last_error and fallback_used:
                out["fallback_reason"] = _brief_error(last_error)
            return out
        except Exception as exc:
            last_error = exc
    raise last_error or RuntimeError("Hermes command failed")


def _normalize_result(payload: dict[str, Any], result: dict[str, Any],
                      active_model: str | None = None, fallback_used: bool = False) -> dict[str, Any]:
    quote = payload.get("quote") or {}
    out = dict(result)
    out["operator"] = "Hermes Agent"
    out["skill"] = out.get("skill") or SKILL
    out["job_id"] = out.get("job_id") or payload.get("job_id")
    out["service"] = out.get("service") or payload.get("service")
    if not isinstance(out.get("operator_runtime"), dict):
        out["operator_runtime"] = _runtime_metadata("completed")
    if not isinstance(out.get("primary_models"), dict):
        out["primary_models"] = _model_roles(active_model, fallback_used)
    else:
        roles = {**_model_roles(active_model, fallback_used), **out["primary_models"]}
        if not isinstance(roles.get("operations_brain"), dict):
            roles["operations_brain"] = {
                **_model_roles(active_model, fallback_used)["operations_brain"],
                "label": roles.get("operations_brain"),
            }
        elif _is_sandbox_runtime() and not active_model:
            roles["operations_brain"] = {
                **roles["operations_brain"],
                "active": NEMOCLAW_INFERENCE_MODEL or "NemoClaw inference.local configured model",
                "active_source": "nemoclaw_inference_route",
            }
        out["primary_models"] = roles
    if not isinstance(out.get("safety_gate"), dict):
        out["safety_gate"] = {
            "model": CONTENT_SAFETY_MODEL,
            "status": "metadata_only",
            "reason": "Bridge received redacted job metadata, not raw dataset contents.",
        }
    out.setdefault("route", "temporarily_queue")
    if not isinstance(out.get("cap"), dict):
        out["cap"] = {
            "quoted_usd": quote.get("quoted_usd"),
            "approved_cap_usd": quote.get("approved_cap_usd"),
            "projected_spend_usd": payload.get("economics", {}).get("actual_cost_usd"),
            "cap_respected": True,
        }
    if not isinstance(out.get("spend_decision"), dict):
        out["spend_decision"] = {
            "needed": out.get("route") == "request_spend",
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
    if not isinstance(out.get("spend"), dict):
        receipt = payload.get("receipt") or {}
        approved_cents = receipt.get("approved_spend_cents")
        out["spend"] = {
            "proposed_by": OPERATIONS_MODEL,
            "approved_cap_cents": approved_cents,
            "projected_spend_cents": approved_cents if payload.get("phase") == "spend_approved" else None,
            "executed": None,
            "cap_respected": True if approved_cents is not None else None,
            "verified_against_stripe": False,
        }
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
        "primary_models": _model_roles(None, False),
        "safety_gate": {
            "model": CONTENT_SAFETY_MODEL,
            "status": "pending",
            "reason": "Operator pass did not complete.",
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
        "spend": {
            "proposed_by": OPERATIONS_MODEL,
            "approved_cap_cents": (payload.get("receipt") or {}).get("approved_spend_cents"),
            "projected_spend_cents": None,
            "executed": None,
            "cap_respected": None,
            "verified_against_stripe": False,
        },
        "operator_runtime": _runtime_metadata("queued"),
        "next_action": "queue",
        "hermes_error": _brief_error(error),
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
        f"Ops model: {((result.get('primary_models') or {}).get('operations_brain') or {}).get('active') or 'unknown'}",
        f"Safety gate: {((result.get('safety_gate') or {}).get('model') or CONTENT_SAFETY_MODEL)}",
        f"Runtime: {((result.get('operator_runtime') or {}).get('runtime') or 'local')}",
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
        _json_response(self, 200, {
            "ok": True,
            "operator": "Hermes Agent",
            "skill": SKILL,
            "operator_runtime": _runtime_metadata("ready"),
        })

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
