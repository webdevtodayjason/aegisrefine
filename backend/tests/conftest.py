"""Shared test fixtures. A session-scoped temp sqlite is bound BEFORE any app import so every
model/engine uses it; tests create their own rows with unique data."""
import os
import sys
import pathlib
import tempfile

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

_DBFILE = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_DBFILE}"
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("COOKIE_SECURE", "0")
os.environ.setdefault("DEV_MODE", "1")

import pytest  # noqa: E402
from app.database import Base, engine, SessionLocal  # noqa: E402
# register every table on Base
from app.models.user import User  # noqa: E402,F401
from app.models.job import Job  # noqa: E402,F401
from app.models.spend_ticket import SpendTicket  # noqa: E402,F401
from app.models.audit_certificate import AuditCertificate  # noqa: E402,F401
from app.models.audit_log import AuditLog  # noqa: E402,F401

Base.metadata.create_all(bind=engine)

_seq = {"n": 0}


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def user(db):
    _seq["n"] += 1
    u = User(email=f"u{_seq['n']}@test.com")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def write_jsonl():
    import json

    def _w(tmp_path, rows):
        p = tmp_path / "raw.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in rows))
        return str(p)
    return _w
