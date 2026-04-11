"""REST endpoints for parametric studies. Prefix: /api/parametric"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from engine_simulator.gui.parametric.parameters import (
    SWEEPABLE_PARAMETERS,
    to_api_dict,
)
from engine_simulator.gui.parametric.schema import ParametricStudyStartRequest
from engine_simulator.gui.parametric.study_manager import (
    ParametricStudyDef,
    _definition_to_dict,
    _run_to_dict,
)


router = APIRouter(prefix="/api/parametric")

_ID_RE = re.compile(r"^[A-Za-z0-9_\-:.]+$")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _make_study_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    return f"param_{ts}"


@router.get("/parameters")
async def list_parameters():
    return [to_api_dict(p) for p in SWEEPABLE_PARAMETERS]


@router.get("/studies")
async def list_studies():
    from engine_simulator.gui import server
    if server.parametric_manager is None:
        return []
    return server.parametric_manager.list_studies()


@router.get("/studies/{study_id}")
async def get_study(study_id: str):
    if not _ID_RE.match(study_id):
        raise HTTPException(status_code=400, detail=f"invalid id: {study_id!r}")
    from engine_simulator.gui import server
    if server.parametric_manager is None:
        raise HTTPException(status_code=503, detail="manager not initialized")
    try:
        server.parametric_manager.load_study(study_id)
    except (FileNotFoundError, ValueError) as exc:
        # load_study raises ValueError for "not found" with a clear message
        if isinstance(exc, FileNotFoundError) or "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=f"study not found: {study_id}")
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    studies_dir = Path(server.parametric_manager._studies_dir)
    file_path = studies_dir / f"{study_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="study file missing")
    with open(file_path) as f:
        return json.load(f)


@router.delete("/studies/{study_id}")
async def delete_study(study_id: str):
    if not _ID_RE.match(study_id):
        raise HTTPException(status_code=400, detail=f"invalid id: {study_id!r}")
    from engine_simulator.gui import server
    if server.parametric_manager is None:
        raise HTTPException(status_code=503, detail="manager not initialized")
    studies_dir = Path(server.parametric_manager._studies_dir)
    file_path = studies_dir / f"{study_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="study not found")
    file_path.unlink()
    return {"deleted": study_id}


@router.post("/study/start")
async def start_study(req: ParametricStudyStartRequest):
    from engine_simulator.gui import server
    if server.parametric_manager is None:
        raise HTTPException(status_code=503, detail="manager not initialized")

    definition = ParametricStudyDef(
        study_id=_make_study_id(),
        name=req.name,
        config_name=req.config_name,
        parameter_path=req.parameter_path,
        parameter_values=req.parameter_values(),
        sweep_rpm_start=req.sweep_rpm_start,
        sweep_rpm_end=req.sweep_rpm_end,
        sweep_rpm_step=req.sweep_rpm_step,
        sweep_n_cycles=req.sweep_n_cycles,
        n_workers=req.n_workers,
        created_at=_iso_now(),
    )

    try:
        study_id = await server.parametric_manager.start_study(definition)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {"study_id": study_id, "status": "running"}


@router.post("/study/stop")
async def stop_study():
    from engine_simulator.gui import server
    if server.parametric_manager is None:
        return {"status": "stopped"}
    await server.parametric_manager.stop_study()
    return {"status": "stopped"}


@router.get("/study/current")
async def get_current_study():
    from engine_simulator.gui import server
    if server.parametric_manager is None:
        return None
    current = server.parametric_manager.get_current()
    if current is None:
        return None
    return {
        "definition": _definition_to_dict(current.definition),
        "status": current.status,
        "started_at": current.started_at,
        "completed_at": current.completed_at,
        "error": current.error,
        "runs": [_run_to_dict(r) for r in current.runs],
    }
