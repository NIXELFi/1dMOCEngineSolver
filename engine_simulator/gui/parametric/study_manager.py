"""ParametricStudyManager — lifecycle owner for parametric studies.

This module holds the data classes only. The manager class itself is
added in a later task.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import traceback as _traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal, Optional

from engine_simulator.gui.parametric.event_consumer import (
    ParametricEventConsumer,
)
from engine_simulator.gui.parametric.parameters import find_parameter
from engine_simulator.gui.parametric.path_resolver import set_parameter
from engine_simulator.simulation.orchestrator import SimulationOrchestrator


logger = logging.getLogger(__name__)


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
    # Keys are stringified floats (JSON round-trip); the value is the
    # last convergence delta observed for that RPM. Stored as strings
    # because JSON does not preserve numeric dict keys.
    per_rpm_delta: dict[str, float] = field(default_factory=dict)
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


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _load_config_dict(config_name: str) -> dict:
    """Load a config JSON file as a raw dict (not an EngineConfig instance)."""
    config_dir = Path(__file__).resolve().parents[2] / "config"
    path = config_dir / config_name
    with open(path) as f:
        return json.load(f)


def _config_from_dict(config_dict: dict):
    """Reconstruct an EngineConfig dataclass instance from a dict.

    Routes through the existing loader that parses the same JSON shape the
    config editor produces. Writes the dict to a temp file then deletes it.
    """
    import tempfile
    from engine_simulator.config.engine_config import load_config

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False,
    ) as f:
        json.dump(config_dict, f)
        tmp_path = f.name
    try:
        return load_config(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


class ParametricStudyManager:
    """Owns the lifecycle of a parametric study.

    Single active study at a time. Spawns a background thread that runs
    one full RPM sweep per parameter value, mutating the base config
    between iterations via the path resolver.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        studies_dir: str,
        broadcast_fn: Callable,
    ):
        self._loop = loop
        self._studies_dir = studies_dir
        self._broadcast = broadcast_fn
        self._current: Optional[LiveParametricStudy] = None
        self._stop_flag = threading.Event()
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="param-study",
        )
        self._study_task: Optional[asyncio.Task] = None

    def get_current(self) -> Optional[LiveParametricStudy]:
        """Return the current study state (live reference, not a copy).

        Note: the returned object is mutated from the background executor
        thread while a study is running. Callers that iterate `runs` or
        `sweep_results` while a sweep is in progress may observe partially
        populated data. For serialization, prefer to call this at a point
        where you know a broadcast has just landed (value_done events are
        safe read points).
        """
        return self._current

    def list_studies(self) -> list[dict]:
        from engine_simulator.gui.parametric.persistence import list_studies
        return list_studies(self._studies_dir)

    def load_study(self, study_id: str) -> LiveParametricStudy:
        from engine_simulator.gui.parametric.persistence import load_study as _load_study
        path = Path(self._studies_dir) / f"{study_id}.json"
        state = _load_study(str(path))
        self._current = state
        return state

    async def start_study(self, definition: ParametricStudyDef) -> str:
        if self._current is not None and self._current.status == "running":
            raise RuntimeError("A parametric study is already running.")

        self._current = LiveParametricStudy(
            definition=definition,
            status="running",
            started_at=_iso_now(),
            runs=[
                ParametricRun(parameter_value=v) for v in definition.parameter_values
            ],
        )
        self._stop_flag.clear()

        await self._broadcast_safe({
            "channel": "parametric",
            "type": "parametric_study_start",
            "study_id": definition.study_id,
            "definition": _definition_to_dict(definition),
        })

        self._study_task = asyncio.create_task(self._run_study())
        return definition.study_id

    async def stop_study(self) -> None:
        """Request the running study to stop at the next value boundary.

        Sets the stop flag and awaits the study task. The flag is only
        checked BETWEEN parameter values, so the currently-executing RPM
        sweep runs to completion before the study exits. This method
        therefore blocks the caller (and the asyncio loop if awaited in
        foreground) until the in-flight sweep finishes. Callers that
        want fire-and-forget semantics should not await the return value.
        """
        if self._current is None or self._current.status != "running":
            return
        self._stop_flag.set()
        if self._study_task is not None:
            try:
                await self._study_task
            except Exception:
                pass

    async def _run_study(self) -> None:
        """Orchestrate the entire study: one RPM sweep per parameter value."""
        try:
            await self._loop.run_in_executor(
                self._executor, self._run_study_blocking,
            )
            if self._stop_flag.is_set():
                self._current.status = "stopped"
            else:
                self._current.status = "complete"
            self._current.completed_at = _iso_now()
            try:
                from engine_simulator.gui.parametric.persistence import save_study
                save_study(self._current, self._studies_dir)
            except Exception:
                logger.exception("failed to save parametric study")
            await self._broadcast_safe({
                "channel": "parametric",
                "type": (
                    "parametric_study_stopped"
                    if self._stop_flag.is_set()
                    else "parametric_study_complete"
                ),
                "study_id": self._current.definition.study_id,
            })
        except Exception as exc:
            self._current.status = "error"
            self._current.error = str(exc)
            self._current.completed_at = _iso_now()
            await self._broadcast_safe({
                "channel": "parametric",
                "type": "parametric_study_error",
                "study_id": self._current.definition.study_id,
                "error_msg": str(exc),
                "traceback": _traceback.format_exc(),
            })

    def _run_study_blocking(self) -> None:
        """Synchronous study loop — runs in the executor thread."""
        definition = self._current.definition
        param = find_parameter(definition.parameter_path)
        if param is None:
            raise RuntimeError(
                f"parameter {definition.parameter_path!r} not in whitelist"
            )

        base_config_dict = _load_config_dict(definition.config_name)

        for idx, value in enumerate(definition.parameter_values):
            if self._stop_flag.is_set():
                return

            run = self._current.runs[idx]
            run.status = "running"
            self._schedule_broadcast({
                "channel": "parametric",
                "type": "parametric_value_start",
                "study_id": definition.study_id,
                "parameter_value": value,
                "value_index": idx,
            })

            start = datetime.now(timezone.utc)
            try:
                mutated_dict = set_parameter(
                    base_config_dict,
                    definition.parameter_path,
                    value,
                    min_allowed=param.min_allowed,
                    max_allowed=param.max_allowed,
                )
                config = _config_from_dict(mutated_dict)
                orchestrator = SimulationOrchestrator(config)

                consumer = ParametricEventConsumer(
                    loop=self._loop,
                    broadcast_fn=self._broadcast,
                    study_id=definition.study_id,
                    parameter_value=value,
                )

                sweep_results = orchestrator.run_rpm_sweep(
                    rpm_start=definition.sweep_rpm_start,
                    rpm_end=definition.sweep_rpm_end,
                    rpm_step=definition.sweep_rpm_step,
                    n_cycles=definition.sweep_n_cycles,
                    verbose=False,
                    n_workers=definition.n_workers,
                    consumer=consumer,
                )

                run.sweep_results = list(sweep_results)
                run.status = "done"
            except Exception as exc:
                run.status = "error"
                run.error = f"{type(exc).__name__}: {exc}\n{_traceback.format_exc()}"

            end = datetime.now(timezone.utc)
            run.elapsed_seconds = (end - start).total_seconds()

            self._schedule_broadcast({
                "channel": "parametric",
                "type": (
                    "parametric_value_done"
                    if run.status == "done"
                    else "parametric_value_error"
                ),
                "study_id": definition.study_id,
                "parameter_value": value,
                "value_index": idx,
                "run": _run_to_dict(run),
            })

    def _schedule_broadcast(self, msg: dict) -> None:
        """Thread-safe: schedule a broadcast on the event loop.

        Logs any exception raised inside the broadcast coroutine instead of
        silently discarding it. A closed loop still swallows RuntimeError.
        """
        try:
            fut = asyncio.run_coroutine_threadsafe(self._broadcast(msg), self._loop)
        except RuntimeError:
            return

        def _log_error(f):
            if f.cancelled():
                return
            exc = f.exception()
            if exc is not None:
                logger.warning("parametric broadcast failed: %s", exc)

        fut.add_done_callback(_log_error)

    async def _broadcast_safe(self, msg: dict) -> None:
        """Async broadcast with error swallowing."""
        try:
            await self._broadcast(msg)
        except Exception:
            logger.exception("broadcast failed")


def _definition_to_dict(d: ParametricStudyDef) -> dict:
    from dataclasses import asdict
    return asdict(d)


def _run_to_dict(r: ParametricRun) -> dict:
    from dataclasses import asdict
    from engine_simulator.gui.persistence import _coerce_jsonable
    return _coerce_jsonable(asdict(r))
