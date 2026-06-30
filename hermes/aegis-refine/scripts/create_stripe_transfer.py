#!/usr/bin/env python3
"""Create a capped Stripe Connect Transfer for an Aegis Refine spend ticket.

This is intentionally small and stdout-only so Hermes can call it from the
aegis-refine skill, then return the resulting transfer id to the backend for
independent verification.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.parse
import urllib.request


def _post_form(url: str, key: str, fields: dict[str, str], idempotency_key: str) -> dict:
    body = urllib.parse.urlencode(fields).encode("utf-8")
    token = base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Idempotency-Key": idempotency_key,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--job-id", required=True)
    p.add_argument("--ticket-id", default="")
    p.add_argument("--amount-cents", required=True, type=int)
    p.add_argument("--service", default="ainode_compute")
    p.add_argument("--purpose", default="agent_spend")
    p.add_argument("--currency", default="usd")
    args = p.parse_args()

    key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    vendor = os.getenv("STRIPE_AGENT_SPEND_VENDOR_ACCOUNT", "").strip()
    max_cents = int(os.getenv("MAX_AGENT_SPEND_CENTS", "5000"))
    amount = min(max(0, args.amount_cents), max_cents)
    if not key or not vendor:
        print(json.dumps({
            "route": "temporarily_queue",
            "spend": {"executed": None, "reason": "stripe spend environment is not configured"},
            "next_action": "queue",
        }))
        return 2
    if amount <= 0:
        print(json.dumps({
            "route": "temporarily_queue",
            "spend": {"executed": None, "reason": "approved spend amount is zero"},
            "next_action": "queue",
        }))
        return 2

    idem = f"{args.job_id}:ticket-{args.ticket_id or args.purpose}"
    fields = {
        "amount": str(amount),
        "currency": args.currency,
        "destination": vendor,
        "metadata[job_id]": args.job_id,
        "metadata[ticket_id]": args.ticket_id,
        "metadata[service]": args.service,
        "metadata[purpose]": args.purpose,
        "metadata[operator]": "Hermes Agent",
        "metadata[skill]": "aegis-refine",
    }
    try:
        transfer = _post_form("https://api.stripe.com/v1/transfers", key, fields, idem)
    except Exception as exc:
        print(json.dumps({
            "route": "temporarily_queue",
            "spend": {"executed": None, "reason": str(exc)[:240]},
            "next_action": "queue",
        }))
        return 1

    print(json.dumps({
        "route": "run_local",
        "spend": {
            "proposed_by": "nvidia/nemotron-3-ultra-550b-a55b",
            "approved_cap_cents": args.amount_cents,
            "projected_spend_cents": amount,
            "executed": {
                "stripe_transfer_id": transfer.get("id"),
                "amount_cents": transfer.get("amount"),
                "currency": transfer.get("currency"),
                "destination": transfer.get("destination"),
                "service": args.service,
                "livemode": transfer.get("livemode"),
            },
            "cap_respected": amount <= args.amount_cents,
            "verified_against_stripe": False,
        },
        "next_action": "continue",
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
