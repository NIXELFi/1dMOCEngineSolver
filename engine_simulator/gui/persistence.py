"""Sweep persistence — save/load LiveSweepState as JSON files in sweeps/.

The file format is a single JSON document per sweep with metadata,
parameters, the engine config snapshot, the perf dict list, and the
per-RPM SimulationResults arrays. See the v1 GUI design spec, Section 6.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from engine_simulator.gui.sweep_manager import LiveSweepState


SCHEMA_VERSION = 1


def _coerce_jsonable(obj):
    """Recursively coerce numpy scalars/arrays to plain Python.

    Also coerces non-finite floats (inf, -inf, nan) to None — JavaScript's
    JSON.parse rejects Python's `Infinity`/`NaN` literals.
    """
    import math
    if isinstance(obj, dict):
        return {str(k): _coerce_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_coerce_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return _coerce_jsonable(obj.tolist())
    if isinstance(obj, np.floating):
        v = float(obj.item())
        return v if math.isfinite(v) else None
    if isinstance(obj, (np.integer, np.bool_)):
        return obj.item()
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    return obj


def _serialize_results(results) -> dict:
    """Convert a SimulationResults instance to a JSON-friendly dict."""
    return {
        "theta_history": _coerce_jsonable(results.theta_history),
        "dt_history": _coerce_jsonable(results.dt_history),
        "plenum_pressure": _coerce_jsonable(results.plenum_pressure),
        "plenum_temperature": _coerce_jsonable(results.plenum_temperature),
        "restrictor_mdot": _coerce_jsonable(results.restrictor_mdot),
        "restrictor_choked": _coerce_jsonable(results.restrictor_choked),
        "cylinder_data": {
            str(cid): {
                "theta": _coerce_jsonable(pd.theta),
                "pressure": _coerce_jsonable(pd.pressure),
                "temperature": _coerce_jsonable(pd.temperature),
                "velocity": _coerce_jsonable(pd.velocity),
                "density": _coerce_jsonable(pd.density),
            }
            for cid, pd in results.cylinder_data.items()
        },
        "pipe_probes": {
            name: {
                "theta": _coerce_jsonable(pd.theta),
                "pressure": _coerce_jsonable(pd.pressure),
                "temperature": _coerce_jsonable(pd.temperature),
                "velocity": _coerce_jsonable(pd.velocity),
                "density": _coerce_jsonable(pd.density),
            }
            for name, pd in results.pipe_probes.items()
        },
    }


def _deserialize_results(d: dict):
    """Convert a JSON dict back into a SimulationResults instance."""
    from engine_simulator.postprocessing.results import SimulationResults, ProbeData

    results = SimulationResults()
    results.theta_history = list(d.get("theta_history", []))
    results.dt_history = list(d.get("dt_history", []))
    results.plenum_pressure = list(d.get("plenum_pressure", []))
    results.plenum_temperature = list(d.get("plenum_temperature", []))
    results.restrictor_mdot = list(d.get("restrictor_mdot", []))
    results.restrictor_choked = list(d.get("restrictor_choked", []))

    for cid_str, probe_dict in d.get("cylinder_data", {}).items():
        pd = ProbeData()
        pd.theta = list(probe_dict.get("theta", []))
        pd.pressure = list(probe_dict.get("pressure", []))
        pd.temperature = list(probe_dict.get("temperature", []))
        pd.velocity = list(probe_dict.get("velocity", []))
        pd.density = list(probe_dict.get("density", []))
        results.cylinder_data[int(cid_str)] = pd

    for name, probe_dict in d.get("pipe_probes", {}).items():
        pd = ProbeData()
        pd.theta = list(probe_dict.get("theta", []))
        pd.pressure = list(probe_dict.get("pressure", []))
        pd.temperature = list(probe_dict.get("temperature", []))
        pd.velocity = list(probe_dict.get("velocity", []))
        pd.density = list(probe_dict.get("density", []))
        results.pipe_probes[name] = pd

    return results


def _build_filename(state) -> str:
    """Build the schema filename for a saved sweep."""
    return f"{state.sweep_id}.json"


def save_sweep(state, sweeps_dir: str) -> str:
    """Save a LiveSweepState to a JSON file in sweeps_dir.

    Writes atomically: first to <name>.tmp, then renames to <name>.
    Returns the filename (not the full path).
    """
    sweeps_path = Path(sweeps_dir)
    sweeps_path.mkdir(parents=True, exist_ok=True)

    filename = _build_filename(state)
    full_path = sweeps_path / filename
    tmp_path = sweeps_path / f"{filename}.tmp"

    duration = 0.0
    if state.completed_at and state.started_at:
        from datetime import datetime
        try:
            start = datetime.fromisoformat(state.started_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(state.completed_at.replace("Z", "+00:00"))
            duration = (end - start).total_seconds()
        except Exception:
            duration = 0.0

    # Serialize the engine config. It might be a dataclass instance OR
    # a raw dict (if loaded from a previous sweep file).
    if hasattr(state.config, "__dataclass_fields__"):
        config_serialized = _coerce_jsonable(asdict(state.config))
    else:
        config_serialized = _coerce_jsonable(state.config)

    document = {
        "schema_version": SCHEMA_VERSION,
        "sweep_id": state.sweep_id,
        "metadata": {
            "started_at": state.started_at,
            "completed_at": state.completed_at,
            "duration_seconds": duration,
            "host": socket.gethostname(),
            "python_version": sys.version.split()[0],
            "n_workers_requested": state.n_workers,
            "n_workers_effective": state.n_workers,
            "config_name": state.config_name,
            "git_status": None,
        },
        "sweep_params": {
            "rpm_start": state.rpm_points[0] if state.rpm_points else 0,
            "rpm_end": state.rpm_points[-1] if state.rpm_points else 0,
            "rpm_step": (
                state.rpm_points[1] - state.rpm_points[0]
                if len(state.rpm_points) > 1 else 0
            ),
            "n_cycles": state.n_cycles,
            "rpm_points": _coerce_jsonable(state.rpm_points),
        },
        "engine_config": config_serialized,
        "perf": _coerce_jsonable(state.sweep_results),
        "results_by_rpm": {
            str(rpm): _serialize_results(results)
            for rpm, results in state.results_by_rpm.items()
        },
        "convergence": {
            str(rpm): {
                "delta_history": _coerce_jsonable(
                    rpm_state.get("delta_history", [])
                ),
                "p_ivc_history": _coerce_jsonable(
                    rpm_state.get("p_ivc_history", [])
                ),
                "converged": rpm_state.get("converged", False),
                "converged_at_cycle": rpm_state.get("converged_at_cycle"),
            }
            for rpm, rpm_state in state.rpms.items()
        },
    }

    with open(tmp_path, "w") as f:
        json.dump(document, f)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp_path, full_path)
    return filename


def load_sweep(file_path: str):
    """Load a sweep file from disk into a LiveSweepState.

    Raises ValueError on parse errors or unknown schema versions.
    """
    try:
        with open(file_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Could not parse {file_path}: {exc}"
        ) from exc
    except FileNotFoundError as exc:
        raise ValueError(f"Sweep file not found: {file_path}") from exc

    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"Sweep file uses schema version {version}, "
            f"this version of the GUI supports up to {SCHEMA_VERSION}. "
            f"Update the GUI or use an older sweep."
        )

    # Lazy import to avoid circular import at module load
    from engine_simulator.gui.sweep_manager import LiveSweepState

    rpm_points = data["sweep_params"].get("rpm_points", [])
    results_by_rpm = {
        float(rpm): _deserialize_results(rd)
        for rpm, rd in data.get("results_by_rpm", {}).items()
    }

    rpms = {
        float(p["rpm"]): {
            "status": "done",
            "rpm_index": idx,
            "perf": p,
        }
        for idx, p in enumerate(data.get("perf", []))
    }

    convergence = data.get("convergence", {})
    for rpm_str, conv_data in convergence.items():
        rpm_key = float(rpm_str)
        if rpm_key in rpms:
            rpms[rpm_key]["delta_history"] = conv_data.get("delta_history", [])
            rpms[rpm_key]["p_ivc_history"] = conv_data.get("p_ivc_history", [])
            rpms[rpm_key]["converged"] = conv_data.get("converged", False)
            rpms[rpm_key]["converged_at_cycle"] = conv_data.get("converged_at_cycle")

    state = LiveSweepState(
        sweep_id=data["sweep_id"],
        status="complete",
        config=data["engine_config"],   # raw dict, not reconstructed EngineConfig
        config_name=data["metadata"].get("config_name", ""),
        rpm_points=[float(r) for r in rpm_points],
        n_cycles=data["sweep_params"].get("n_cycles", 0),
        n_workers=data["metadata"].get("n_workers_effective", 0),
        started_at=data["metadata"].get("started_at", ""),
        completed_at=data["metadata"].get("completed_at"),
        rpms=rpms,
        results_by_rpm=results_by_rpm,
        sweep_results=data.get("perf", []),
    )
    return state


def list_sweeps(sweeps_dir: str) -> list:
    """List the saved sweeps in sweeps_dir, newest first.

    Returns a list of summary dicts (id, filename, started_at, etc.)
    suitable for the GUI's "available sweeps" dropdown.
    """
    sweeps_path = Path(sweeps_dir)
    if not sweeps_path.exists():
        return []

    summaries = []
    for path in sorted(sweeps_path.glob("*.json"), reverse=True):
        if path.name.endswith(".tmp"):
            continue
        try:
            with open(path) as f:
                data = json.load(f)
            rpm_points = data.get("sweep_params", {}).get("rpm_points", [])
            summaries.append({
                "id": data.get("sweep_id", path.stem),
                "filename": path.name,
                "started_at": data.get("metadata", {}).get("started_at", ""),
                "duration_seconds": data.get("metadata", {}).get(
                    "duration_seconds", 0.0
                ),
                "rpm_range": [
                    rpm_points[0] if rpm_points else 0,
                    rpm_points[-1] if rpm_points else 0,
                ],
                "n_rpm_points": len(rpm_points),
            })
        except Exception:
            continue
    return summaries
