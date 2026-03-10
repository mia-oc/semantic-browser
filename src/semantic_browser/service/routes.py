"""HTTP routes for local service mode."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from semantic_browser.models import ActionRequest
from semantic_browser.session import ManagedSession
from semantic_browser.service.schemas import ActRequest, InspectRequest, LaunchRequest, NavigateRequest, ObserveRequest

router = APIRouter()
_sessions: dict[str, ManagedSession] = {}


@router.post("/sessions/launch")
async def launch_session(req: LaunchRequest):
    session = await ManagedSession.launch(headful=req.headful)
    sid = session.runtime.session_id
    _sessions[sid] = session
    return {"session_id": sid}


@router.post("/sessions/{session_id}/close")
async def close_session(session_id: str):
    session = _sessions.pop(session_id, None)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    await session.close()
    return {"ok": True}


@router.post("/sessions/{session_id}/observe")
async def observe(session_id: str, req: ObserveRequest):
    runtime = _get_runtime(session_id)
    observation = await runtime.observe(mode=req.mode)
    return observation.model_dump(mode="json")


@router.post("/sessions/{session_id}/inspect")
async def inspect(session_id: str, req: InspectRequest):
    runtime = _get_runtime(session_id)
    return await runtime.inspect(req.target_id)


@router.post("/sessions/{session_id}/navigate")
async def navigate(session_id: str, req: NavigateRequest):
    runtime = _get_runtime(session_id)
    result = await runtime.navigate(req.url)
    return result.model_dump(mode="json")


@router.post("/sessions/{session_id}/act")
async def act(session_id: str, req: ActRequest):
    runtime = _get_runtime(session_id)
    result = await runtime.act(req.action)
    return result.model_dump(mode="json")


@router.get("/sessions/{session_id}/diagnostics")
async def diagnostics(session_id: str):
    runtime = _get_runtime(session_id)
    return (await runtime.diagnostics()).model_dump(mode="json")


@router.post("/sessions/{session_id}/export-trace")
async def export_trace(session_id: str):
    runtime = _get_runtime(session_id)
    path = await runtime.export_trace(f"trace-{session_id}.json")
    return {"path": path}


def _get_runtime(session_id: str):
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return session.runtime
