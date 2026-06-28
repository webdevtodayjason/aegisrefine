"""Best-effort transactional email via Resend. Never raises into a completed job — a mail
hiccup must not undo a real, signed deliverable. No key / no recipient -> silent no-op.

ponytail: stdlib urllib, no SDK. Set RESEND_API_KEY (+ optional RESEND_FROM) in env.
The sending domain in RESEND_FROM must be verified in Resend or sends are rejected.
"""
import os
import json
import urllib.request


def email_job_done(to_email: str, job_id: int, service: str = "refine") -> bool:
    key = os.getenv("RESEND_API_KEY")
    if not key or not to_email or to_email.endswith("@try.aegisrefine.com"):
        return False
    label = "synthetic dataset" if service == "synthesis" else "refined dataset"
    sender = os.getenv("RESEND_FROM", "Aegis Refine <noreply@aegisrefine.com>")
    body = {
        "from": sender,
        "to": [to_email],
        "subject": f"Your {label} is ready — job #{job_id}",
        "html": (f"<p>Your {label} (job #{job_id}) is ready.</p>"
                 f"<p><a href=\"https://aegisrefine.com/order-detail.html?job={job_id}\">"
                 f"Download it and view the signed certificate →</a></p>"
                 f"<p style=\"color:#888;font-size:12px\">Aegis Refine · every row PII-masked, deduped, "
                 f"schema-valid, with a re-verifiable certificate.</p>"),
    }
    try:
        req = urllib.request.Request(
            "https://api.resend.com/emails", data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        return False  # best-effort
