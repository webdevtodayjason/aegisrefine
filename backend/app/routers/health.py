import os
import time

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from app.services import agent

router = APIRouter(prefix="/agent", tags=["health"])


@router.get("/health")
async def agent_health():
    model_name = os.getenv("AINODE_MODEL", "Aegis-14B")
    started = time.perf_counter()
    try:
        await run_in_threadpool(
            agent.decide,
            "triage",
            "Aegis-14B health probe. Return the required triage JSON for a tiny local reachability check.",
            model=model_name,
            retries=0,
        )
    except Exception as exc:
        return {
            "status": "degraded",
            "model_name": model_name,
            "error": str(exc),
        }
    return {
        "status": "ok",
        "model_name": model_name,
        "latency_ms": max(0, round((time.perf_counter() - started) * 1000)),
    }
