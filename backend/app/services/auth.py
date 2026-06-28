"""
Authentication — stdlib only (no new deps, no container build risk).
pbkdf2-sha256 password hashing + an HMAC-SHA256-signed session cookie.
"""
import os
import hmac
import json
import time
import base64
import hashlib
import secrets as _secrets

from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User

SECRET = (os.getenv("SECRET_KEY") or "dev-only-secret").encode()
COOKIE = "aegis_session"
SESSION_TTL = 7 * 24 * 3600  # 7 days
_ITER = 600_000


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _ub64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(pw: str) -> str:
    salt = _secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, _ITER)
    return f"pbkdf2${_ITER}${_b64(salt)}${_b64(dk)}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, iters, salt_b64, hash_b64 = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), _ub64(salt_b64), int(iters))
        return hmac.compare_digest(dk, _ub64(hash_b64))
    except Exception:
        return False


def make_token(user: User) -> str:
    body = _b64(json.dumps({"uid": user.id, "adm": bool(user.is_admin),
                            "exp": int(time.time()) + SESSION_TTL}).encode())
    sig = _b64(hmac.new(SECRET, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(token: str):
    try:
        body, sig = token.split(".")
        expected = _b64(hmac.new(SECRET, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_ub64(body))
        return None if payload.get("exp", 0) < time.time() else payload
    except Exception:
        return None


def current_user(request: Request, db: Session = Depends(get_db)):
    tok = request.cookies.get(COOKIE)
    if not tok:
        return None
    payload = read_token(tok)
    if not payload:
        return None
    return db.query(User).filter(User.id == payload["uid"]).first()


def require_user(user: User = Depends(current_user)) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="login required")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="admin only")
    return user
