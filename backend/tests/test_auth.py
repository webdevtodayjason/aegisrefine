from starlette.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models.user import User
from app.services.auth import hash_password


def _client():
    return TestClient(app, follow_redirects=False)


def test_signup_login_logout_and_page_gate():
    c = _client()
    assert c.get("/login.html").status_code == 200
    r = c.get("/dashboard.html")
    assert r.status_code == 302 and "/login.html" in r.headers["location"]

    r = c.post("/auth/signup", json={"email": "member-a@test.com", "password": "hunter2pass"})
    assert r.status_code == 200
    assert c.get("/dashboard.html").status_code == 200      # authed page loads
    assert c.get("/jobs/").status_code == 200               # authed API works
    assert c.get("/ops.html").status_code == 302            # non-admin blocked from ops

    c.post("/auth/logout")
    assert c.get("/dashboard.html").status_code == 302       # re-gated
    assert c.get("/jobs/").status_code == 401                # API re-gated


def test_admin_role_gate():
    db = SessionLocal()
    db.add(User(email="admin-a@test.com", password_hash=hash_password("adminpass1"), is_admin=True))
    db.commit()
    c = _client()
    r = c.post("/auth/login", json={"email": "admin-a@test.com", "password": "adminpass1"})
    assert r.status_code == 200 and r.json()["is_admin"] is True
    assert c.get("/ops.html").status_code == 200            # admin reaches ops


def test_public_audit_feed_stays_open():
    assert _client().get("/activity").status_code == 200
