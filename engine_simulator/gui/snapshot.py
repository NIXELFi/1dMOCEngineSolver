"""Build a JSON-serializable snapshot of the current sweep state.

Sent to every newly-connected WebSocket client so they can render the
in-progress (or last-finished) sweep without missing any events.
"""

from __future__ import annotations

from typing import Optional

from engine_simulator.gui.persistence import list_sweeps, _coerce_jsonable


def _serialize_rpms(rpms: dict) -> dict:
    out = {}
    for rpm, rpm_state in rpms.items():
        out[str(rpm)] = _coerce_jsonable(rpm_state)
    return out


def build_snapshot(current, sweeps_dir: str) -> dict:
    """Build a snapshot dict from the current LiveSweepState (or None).

    The result is the payload of a `snapshot` WebSocket message.
    """
    available = list_sweeps(sweeps_dir)

    if current is None:
        return {
            "type": "snapshot",
            "sweep": None,
            "available_sweeps": available,
        }

    rpm_points_list = list(current.rpm_points)
    rpm_step = (
        rpm_points_list[1] - rpm_points_list[0]
        if len(rpm_points_list) >= 2 else 0
    )

    sweep_payload = {
        "status": current.status,
        "sweep_id": current.sweep_id,
        "config_summary": {
            "rpm_start": rpm_points_list[0] if rpm_points_list else 0,
            "rpm_end": rpm_points_list[-1] if rpm_points_list else 0,
            "rpm_step": rpm_step,
            "n_cycles": current.n_cycles,
            "n_workers": current.n_workers,
            "config_name": current.config_name,
        },
        "rpm_points": _coerce_jsonable(rpm_points_list),
        "started_at": current.started_at,
        "elapsed_seconds": 0.0,
        "rpms": _serialize_rpms(current.rpms),
        "results_by_rpm_summary": {
            str(rpm): {"available": True}
            for rpm in current.results_by_rpm.keys()
        },
    }

    return {
        "type": "snapshot",
        "sweep": sweep_payload,
        "available_sweeps": available,
    }
