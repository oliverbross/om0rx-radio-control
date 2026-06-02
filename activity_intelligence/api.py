"""FastAPI router for Activity Intelligence dashboards and controls."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request

from .services import get_activity_intelligence_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/activity-intelligence")
async def get_activity_dashboard():
    try:
        return get_activity_intelligence_service().dashboard()
    except Exception as exc:
        logger.error("Activity dashboard error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/activity-intelligence/refresh")
async def refresh_activity_sources(force: bool = Query(default=True)):
    try:
        return await get_activity_intelligence_service().refresh_due_sources(force=force)
    except Exception as exc:
        logger.error("Activity refresh error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/activity-intelligence/reference")
async def lookup_portable_reference(q: str = Query(default="")):
    try:
        return await get_activity_intelligence_service().lookup_reference_extended(q)
    except Exception as exc:
        logger.error("Activity reference lookup error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/activity-intelligence/dxpeditions/{dxpedition_id:path}")
async def get_dxpedition_detail(dxpedition_id: str, request: Request):
    try:
        classifier = getattr(request.app.state, "classifier", None)
        result = await get_activity_intelligence_service().dxpedition_detail(dxpedition_id, classifier)
        if not result.get("ok"):
            raise HTTPException(status_code=404, detail=result.get("error", "DXpedition not found"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("DXpedition detail error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/activity-intelligence/rbn")
async def get_rbn_summary(minutes: int = Query(default=60, ge=1, le=1440)):
    try:
        service = get_activity_intelligence_service()
        return {"ok": True, "rbn": service.rbn_summary(minutes=minutes)}
    except Exception as exc:
        logger.error("RBN summary error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/activity-intelligence/contest-context")
async def set_contest_context(payload: dict):
    try:
        contest_id = payload.get("contestId") or payload.get("contest_id")
        result = get_activity_intelligence_service().set_contest_context(contest_id)
        if not result.get("ok"):
            raise HTTPException(status_code=404, detail=result.get("error", "Contest not found"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Contest context error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
