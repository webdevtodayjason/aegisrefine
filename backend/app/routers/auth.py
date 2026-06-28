import os
import secrets
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.services import auth

router = APIRouter(prefix="/auth", tags=["auth"])
SECURE = os.getenv("COOKIE_SECURE", "1") == "1"  # set 0 for local http testing


class Creds(BaseModel):
    email: str
    password: str


def _set_session(resp: Response, user: User):
    resp.set_cookie(auth.COOKIE, auth.make_token(user), max_age=auth.SESSION_TTL,
                    httponly=True, secure=SECURE, samesite="lax", path="/")


@router.post("/signup")
async def signup(c: Creds, resp: Response, db: Session = Depends(get_db)):
    email = c.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1] or len(c.password) < 8:
        raise HTTPException(status_code=400, detail="A valid email and an 8+ character password are required")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account with that email already exists")
    user = User(email=email, password_hash=auth.hash_password(c.password), is_admin=False)
    db.add(user); db.commit(); db.refresh(user)
    _set_session(resp, user)
    return {"id": user.id, "email": user.email, "is_admin": user.is_admin}


@router.post("/login")
async def login(c: Creds, resp: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == c.email.strip().lower()).first()
    if not user or not user.password_hash or not auth.verify_password(c.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    _set_session(resp, user)
    return {"id": user.id, "email": user.email, "is_admin": user.is_admin}


@router.post("/logout")
async def logout(resp: Response):
    # attributes must match _set_session or the browser won't drop the cookie
    resp.delete_cookie(auth.COOKIE, path="/", samesite="lax", secure=SECURE, httponly=True)
    return {"ok": True}


@router.get("/try")
async def instant_try(db: Session = Depends(get_db)):
    """Zero-friction tester access (magic link): provision a FRESH demo account, log in, and drop
    straight into the wizard — no signup form. Each visit is its own clean workspace."""
    email = f"tester-{secrets.token_hex(4)}@try.aegisrefine.com"
    user = User(email=email, password_hash=auth.hash_password(secrets.token_urlsafe(18)), is_admin=False)
    db.add(user); db.commit(); db.refresh(user)
    redirect = RedirectResponse(url="/new-order.html", status_code=303)
    _set_session(redirect, user)
    return redirect


@router.get("/me")
async def me(user: User = Depends(auth.current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="not logged in")
    return {"id": user.id, "email": user.email, "is_admin": user.is_admin}
