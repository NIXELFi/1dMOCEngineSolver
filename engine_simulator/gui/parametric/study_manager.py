"""ParametricStudyManager — lifecycle owner for parametric studies.

This module holds the data classes only. The manager class itself is
added in a later task.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class ParametricStudyDef:
    """User-submitted definition of a parametric study."""
    study_id: str
    name: str
    config_name: str
    parameter_path: str
    parameter_values: list[float]
    sweep_rpm_start: float
    sweep_rpm_end: float
    sweep_rpm_step: float
    sweep_n_cycles: int
    n_workers: int
    created_at: str


@dataclass
class ParametricRun:
    """Result of running the RPM sweep for a single parameter value."""
    parameter_value: float
    status: Literal["queued", "running", "done", "error"] = "queued"
    sweep_results: list[dict] = field(default_factory=list)
    per_rpm_delta: dict = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    error: Optional[str] = None


@dataclass
class LiveParametricStudy:
    """In-memory + persisted study state.

    Serializes directly to the on-disk JSON format.
    """
    definition: ParametricStudyDef
    status: Literal["running", "complete", "error", "stopped"] = "running"
    started_at: str = ""
    completed_at: Optional[str] = None
    runs: list[ParametricRun] = field(default_factory=list)
    error: Optional[str] = None
