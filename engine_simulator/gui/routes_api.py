"""REST endpoints for the GUI server."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine_simulator.gui.config_schema import EnginePayload


router = APIRouter(prefix="/api")


_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]+\.json$")


def _validate_name(name: str) -> str:
    if not _NAME_RE.match(name):
        raise HTTPException(status_code=400, detail=f"Invalid config name: {name!r}")
    return name


# Default directory resolvers — overridable in tests via monkeypatch
def get_configs_dir() -> str:
    return str(Path(__file__).resolve().parents[1] / "config")


def get_sweeps_dir() -> str:
    return str(Path(__file__).resolve().parents[2] / "sweeps")


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/configs")
async def list_configs():
    configs_dir = Path(get_configs_dir())
    if not configs_dir.exists():
        return []
    out = []
    for path in sorted(configs_dir.glob("*.json")):
        out.append({
            "name": path.name,
            "path": str(path),
            "summary": "",
        })
    return out


@router.get("/configs/{name}")
async def get_config(name: str):
    import json
    config_path = Path(get_configs_dir()) / name
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"Config not found: {name}")
    with open(config_path) as f:
        return json.load(f)


@router.put("/configs/{name}")
async def save_config(name: str, payload: EnginePayload):
    name = _validate_name(name)
    config_path = Path(get_configs_dir()) / name
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"Config not found: {name}")
    config_path.write_text(payload.model_dump_json(indent=4))
    return payload.model_dump(mode="json")


class SaveAsRequest(BaseModel):
    name: str
    payload: EnginePayload


@router.post("/configs")
async def save_config_as(req: SaveAsRequest):
    name = _validate_name(req.name)
    config_path = Path(get_configs_dir()) / name
    if config_path.exists():
        raise HTTPException(
            status_code=409, detail=f"Config already exists: {name}"
        )
    config_path.write_text(req.payload.model_dump_json(indent=4))
    return req.payload.model_dump(mode="json")


@router.get("/sweeps")
async def list_sweeps_endpoint():
    from engine_simulator.gui.persistence import list_sweeps
    return list_sweeps(get_sweeps_dir())


@router.get("/sweeps/{sweep_id}")
async def get_sweep(sweep_id: str):
    from engine_simulator.gui.persistence import load_sweep
    from engine_simulator.gui.snapshot import build_snapshot
    from engine_simulator.gui import server

    sweeps_dir = Path(get_sweeps_dir())
    file_path = sweeps_dir / f"{sweep_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Sweep not found: {sweep_id}")
    try:
        state = load_sweep(str(file_path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Set the loaded sweep as the current state and broadcast a snapshot
    # so all connected WS clients update their UI with the loaded sweep.
    if server.sweep_manager is not None:
        server.sweep_manager._current = state
        try:
            snapshot_msg = build_snapshot(state, str(sweeps_dir))
            await server.sweep_manager._broadcast_fn(snapshot_msg)
        except Exception:
            pass  # broadcast failure must not block the HTTP response

    import json
    with open(file_path) as f:
        return json.load(f)


class SweepStartParams(BaseModel):
    rpm_start: float = Field(..., gt=0)
    rpm_end: float = Field(..., gt=0)
    rpm_step: float = Field(..., gt=0)
    n_cycles: int = Field(..., gt=0, le=100)
    n_workers: int = Field(..., gt=0, le=64)
    config_name: str = Field(...)


@router.post("/sweep/start")
async def start_sweep(params: SweepStartParams):
    from engine_simulator.gui import server
    if server.sweep_manager is None:
        raise HTTPException(
            status_code=503,
            detail="Sweep manager not initialized",
        )
    try:
        sweep_id = await server.sweep_manager.start_sweep(params.dict())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"sweep_id": sweep_id, "status": "running"}


@router.post("/sweep/stop")
async def stop_sweep():
    from engine_simulator.gui import server
    if server.sweep_manager is None:
        return {"status": "stopped"}
    await server.sweep_manager.stop_sweep()
    return {"status": "stopped"}


@router.get("/sweeps/current/results/{rpm}")
async def get_current_sweep_results(rpm: float):
    from engine_simulator.gui import server
    from engine_simulator.gui.persistence import _serialize_results

    if server.sweep_manager is None or server.sweep_manager.current is None:
        raise HTTPException(status_code=404, detail="No current sweep")

    state = server.sweep_manager.current
    results = state.results_by_rpm.get(float(rpm))
    if results is None:
        raise HTTPException(
            status_code=404,
            detail=f"No recorded results for RPM {rpm}",
        )
    return _serialize_results(results)
