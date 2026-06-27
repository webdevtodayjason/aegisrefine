# Aegis Backend

FastAPI backend for Aegis — Conductor-governed autonomous dataset refinery.

## Stack
- FastAPI
- PostgreSQL
- Conductor orchestration
- Stripe Skills
- AInode on Spark 1

## Structure
- `app/main.py` — FastAPI entrypoint
- `app/models/` — SQLAlchemy models
- `app/routers/` — API routes
- `app/services/` — Business logic
- `app/conductor/` — Conductor integration layer

## Getting Started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Next
- Conductor node integration
- Stripe webhook handling
- Gated spend flow
- Audit certificate generation