"""Save/load LiveParametricStudy as JSON files under sweeps/parametric/.

Studies are stored separately from regular sweeps so the UI can list and
load them independently.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from engine_simulator.gui.parametric.study_manager import (
    LiveParametricStudy,
    ParametricRun,
    ParametricStudyDef,
)
from engine_simulator.gui.persistence import _coerce_jsonable


SCHEMA_VERSION = 1


def save_study(study: LiveParametricStudy, studies_dir: str) -> str:
    """Save a study to `<studies_dir>/<study_id>.json`. Returns the filename."""
    Path(studies_dir).mkdir(parents=True, exist_ok=True)
    filename = f"{study.definition.study_id}.json"
    path = Path(studies_dir) / filename

    payload = {
        "schema_version": SCHEMA_VERSION,
        "definition": asdict(study.definition),
        "status": study.status,
        "started_at": study.started_at,
        "completed_at": study.completed_at,
        "error": study.error,
        "runs": [asdict(run) for run in study.runs],
    }
    safe = _coerce_jsonable(payload)
    path.write_text(json.dumps(safe, indent=2))
    return filename


def load_study(path: str) -> LiveParametricStudy:
    """Load a study from the given JSON file path.

    Raises ValueError for missing files, malformed JSON, unknown schema
    versions, or missing required fields. The caller gets a single,
    descriptive error in every failure mode.
    """
    try:
        with open(path) as f:
            payload = json.load(f)
    except FileNotFoundError as exc:
        raise ValueError(f"Study file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse {path}: {exc}") from exc

    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"{path}: schema_version {version!r} not supported "
            f"(expected {SCHEMA_VERSION})"
        )

    try:
        definition = ParametricStudyDef(**payload["definition"])
        runs = [ParametricRun(**r) for r in payload.get("runs", [])]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"{path}: malformed study payload: {exc}") from exc

    return LiveParametricStudy(
        definition=definition,
        status=payload.get("status", "complete"),
        started_at=payload.get("started_at", ""),
        completed_at=payload.get("completed_at"),
        runs=runs,
        error=payload.get("error"),
    )


def list_studies(studies_dir: str) -> list[dict]:
    """Return metadata for every saved study, newest first.

    Each entry:
    - study_id, name, parameter_path, created_at, status, run_count,
      parameter_values (count only)
    """
    dir_path = Path(studies_dir)
    if not dir_path.exists():
        return []

    items = []
    for path in sorted(dir_path.glob("*.json"), reverse=True):
        try:
            with open(path) as f:
                payload = json.load(f)
            def_ = payload.get("definition", {})
            items.append({
                "study_id": def_.get("study_id", path.stem),
                "name": def_.get("name", ""),
                "parameter_path": def_.get("parameter_path", ""),
                "n_values": len(def_.get("parameter_values", [])),
                "created_at": def_.get("created_at", ""),
                "status": payload.get("status", "unknown"),
                "run_count": len(payload.get("runs", [])),
            })
        except (OSError, json.JSONDecodeError, KeyError):
            continue
    return items
