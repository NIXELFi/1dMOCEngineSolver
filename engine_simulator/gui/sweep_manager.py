"""SweepManager — owns the lifecycle of a parallel sweep for the GUI.

Wraps the existing ParallelSweepRunner with an asyncio-friendly facade:
- start_sweep() kicks off a sweep in a background thread
- A drain task pulls events from the GUIEventConsumer's queue and
  updates LiveSweepState
- On completion, save_sweep() persists the result to disk
- stop_sweep() cancels the sweep and kills worker processes
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _make_sweep_id(params: dict) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    return (
        f"{ts}_{int(params['rpm_start'])}-{int(params['rpm_end'])}"
        f"_step{int(params['rpm_step'])}_{params['n_cycles']}cyc"
    )


def _coerce_jsonable(obj):
    """Recursively coerce numpy scalars/arrays to plain Python types
    so the result is JSON-serializable.

    Critically, this also coerces non-finite floats (inf, -inf, nan) to None.
    Python's json.dumps emits these as the literals `Infinity` / `-Infinity`
    / `NaN`, which are NOT valid JSON and cause JavaScript's JSON.parse to
    throw a SyntaxError. The convergence checker emits delta=inf on the very
    first cycle of each RPM (no previous cycle to compare against), and
    without this coercion the resulting cycle_done event is undeliverable
    to the browser.
    """
    import math
    import numpy as np
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


def _resolve_config_path(config_name: str) -> str:
    """Resolve a bare config name (e.g. 'cbr600rr.json') to a full
    path under engine_simulator/config/."""
    config_dir = Path(__file__).resolve().parents[1] / "config"
    return str(config_dir / config_name)


def load_config(path):
    """Lazy wrapper around engine_simulator.config.engine_config.load_config."""
    from engine_simulator.config.engine_config import load_config as _lc
    return _lc(path)


def save_sweep(state, sweeps_dir):
    """Lazy wrapper around engine_simulator.gui.persistence.save_sweep.

    Imported lazily because persistence.py is built in Phase E. Until then,
    this raises ImportError when called — which is fine because tests stub it.
    """
    from engine_simulator.gui.persistence import save_sweep as _ss
    return _ss(state, sweeps_dir)


@dataclass
class LiveSweepState:
    """Single source of truth for the currently-running (or last-finished) sweep.

    Mutated by the event drain task as events arrive. Read by the WebSocket
    snapshot endpoint, the REST endpoints, and the persistence layer.
    """
    sweep_id: str
    status: str                                  # "running" | "complete" | "error" | "stopped"
    config: Any                                  # EngineConfig instance
    config_name: str
    rpm_points: list                             # list[float]
    n_cycles: int
    n_workers: int
    started_at: str                              # ISO timestamp
    completed_at: Optional[str] = None
    rpms: dict = field(default_factory=dict)     # rpm (float) -> per-rpm state dict
    results_by_rpm: dict = field(default_factory=dict)   # rpm (float) -> SimulationResults
    sweep_results: list = field(default_factory=list)    # ordered list of perf dicts
    error_msg: Optional[str] = None
    error_traceback: Optional[str] = None


class SweepManager:
    """Owns sweep lifecycle for the GUI: start, stop, drain events, save."""

    def __init__(self, loop, sweeps_dir: str, broadcast_fn):
        self._loop = loop
        self._sweeps_dir = sweeps_dir
        self._broadcast_fn = broadcast_fn
        self._current: Optional[LiveSweepState] = None
        self._sweep_task: Optional[asyncio.Task] = None
        self._drain_task: Optional[asyncio.Task] = None
        self._consumer = None
        # ParallelSweepRunner.run() is blocking. We run it in a single
        # thread so the asyncio loop stays responsive. The runner internally
        # spawns the actual ProcessPoolExecutor for the workers.
        self._runner_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="sweep-runner",
        )

    @property
    def current(self) -> Optional[LiveSweepState]:
        return self._current

    def _apply_event(self, event):
        """Mutate self._current.rpms based on the event type.

        Called from the drain task on the asyncio loop. Pure state mutation —
        broadcasting is done separately by the caller.
        """
        from engine_simulator.simulation.parallel_sweep import (
            ConvergedEvent, CycleDoneEvent, RPMDoneEvent,
            RPMErrorEvent, RPMStartEvent,
        )

        rpm = float(event.rpm)
        if rpm not in self._current.rpms:
            return
        rpm_state = self._current.rpms[rpm]

        if isinstance(event, RPMStartEvent):
            rpm_state.update({
                "status": "running",
                "current_cycle": 0,
                "rpm_index": event.rpm_index,
                "delta_history": [],
                "p_ivc_history": [],
                "step_count": 0,
                "elapsed": 0.0,
            })
        elif isinstance(event, CycleDoneEvent):
            import math
            # Coerce non-finite delta (the convergence checker emits inf
            # on the first cycle of each RPM) so that the snapshot rebuilt
            # later doesn't contain Infinity, which JavaScript can't parse.
            delta_safe = (
                event.delta
                if event.delta is not None and math.isfinite(event.delta)
                else None
            )
            rpm_state["current_cycle"] = event.cycle
            rpm_state["delta"] = delta_safe
            rpm_state.setdefault("delta_history", []).append(delta_safe)
            rpm_state.setdefault("p_ivc_history", []).append(list(event.p_ivc))
            rpm_state["step_count"] = event.step_count
            rpm_state["elapsed"] = event.elapsed
        elif isinstance(event, ConvergedEvent):
            rpm_state["converged_at_cycle"] = event.cycle
        elif isinstance(event, RPMDoneEvent):
            rpm_state.update({
                "status": "done",
                "perf": event.perf,
                "elapsed": event.elapsed,
                "step_count": event.step_count,
                "converged": event.converged,
            })
        elif isinstance(event, RPMErrorEvent):
            rpm_state.update({
                "status": "error",
                "error_type": event.error_type,
                "error_msg": event.error_msg,
                "traceback": event.traceback,
            })

    def _event_to_json(self, event):
        """Translate a Python event dataclass to a JSON-serializable dict."""
        from engine_simulator.simulation.parallel_sweep import (
            ConvergedEvent, CycleDoneEvent, RPMDoneEvent,
            RPMErrorEvent, RPMStartEvent,
        )

        if isinstance(event, RPMStartEvent):
            return {
                "type": "rpm_start", "rpm": event.rpm,
                "rpm_index": event.rpm_index,
                "n_cycles_target": event.n_cycles_target, "ts": event.ts,
            }
        elif isinstance(event, CycleDoneEvent):
            return {
                "type": "cycle_done", "rpm": event.rpm, "cycle": event.cycle,
                "delta": event.delta, "p_ivc": list(event.p_ivc),
                "step_count": event.step_count,
                "elapsed": event.elapsed, "ts": event.ts,
            }
        elif isinstance(event, ConvergedEvent):
            return {
                "type": "converged", "rpm": event.rpm,
                "cycle": event.cycle, "ts": event.ts,
            }
        elif isinstance(event, RPMDoneEvent):
            return {
                "type": "rpm_done", "rpm": event.rpm,
                "perf": _coerce_jsonable(event.perf),
                "elapsed": event.elapsed,
                "step_count": event.step_count,
                "converged": event.converged, "ts": event.ts,
                "results_available": True,
            }
        elif isinstance(event, RPMErrorEvent):
            return {
                "type": "rpm_error", "rpm": event.rpm,
                "error_type": event.error_type,
                "error_msg": event.error_msg,
                "traceback": event.traceback, "ts": event.ts,
            }
        return {"type": "unknown"}

    async def _drain_events(self):
        """Drain GUIEventConsumer.queue, apply state mutations, broadcast."""
        assert self._consumer is not None
        while True:
            event = await self._consumer.queue.get()
            if event is None:
                return
            self._apply_event(event)
            try:
                # Final defensive coerce: any inf/nan that slipped through
                # gets converted to None here so the message is valid JSON
                # for the browser's JSON.parse.
                payload = _coerce_jsonable(self._event_to_json(event))
                await self._broadcast_fn(payload)
            except Exception:
                pass

    def _run_sweep_blocking(self, params: dict):
        """Synchronous: runs in the runner thread. Calls the existing
        SimulationOrchestrator unchanged."""
        from engine_simulator.simulation.orchestrator import (
            SimulationOrchestrator,
        )

        sim = SimulationOrchestrator(self._current.config)
        sweep_results = sim.run_rpm_sweep(
            rpm_start=params["rpm_start"],
            rpm_end=params["rpm_end"],
            rpm_step=params["rpm_step"],
            n_cycles=params["n_cycles"],
            verbose=False,
            n_workers=params["n_workers"],
            consumer=self._consumer,
        )
        self._current.sweep_results = sweep_results
        self._current.results_by_rpm = dict(sim.results_by_rpm)

    async def _run_sweep_in_thread(self, params: dict):
        """Run the sweep in a thread, then save and broadcast completion."""
        try:
            await self._loop.run_in_executor(
                self._runner_executor,
                self._run_sweep_blocking,
                params,
            )
            # Ensure the drain task can terminate. The real solver closes
            # the consumer internally; this is an idempotent safety net for
            # stub solvers in tests and any code path that doesn't close.
            if self._consumer is not None:
                self._consumer.close()
            # Wait for the drain task to process any remaining events
            # including the close sentinel
            if self._drain_task is not None:
                try:
                    await asyncio.wait_for(self._drain_task, timeout=5.0)
                except asyncio.TimeoutError:
                    pass

            self._current.status = "complete"
            self._current.completed_at = _iso_now()

            filename = save_sweep(self._current, self._sweeps_dir)
            duration = self._compute_duration()
            await self._broadcast_fn({
                "type": "sweep_complete",
                "sweep_id": self._current.sweep_id,
                "filename": filename,
                "duration_seconds": duration,
            })
        except asyncio.CancelledError:
            self._current.status = "stopped"
            await self._broadcast_fn({
                "type": "sweep_complete",
                "sweep_id": self._current.sweep_id,
                "stopped": True,
            })
            raise
        except Exception as exc:
            import traceback
            self._current.status = "error"
            self._current.error_msg = str(exc)
            self._current.error_traceback = traceback.format_exc()
            await self._broadcast_fn({
                "type": "sweep_error",
                "error_msg": str(exc),
                "traceback": traceback.format_exc(),
            })

    def _compute_duration(self) -> float:
        try:
            start = datetime.fromisoformat(
                self._current.started_at.replace("Z", "+00:00")
            )
            end = datetime.fromisoformat(
                (self._current.completed_at or _iso_now()).replace("Z", "+00:00")
            )
            return (end - start).total_seconds()
        except Exception:
            return 0.0

    async def start_sweep(self, params: dict) -> str:
        """Start a sweep. Returns the sweep_id. Raises if one is already running."""
        if self._current is not None and self._current.status == "running":
            raise RuntimeError(
                "A sweep is already running. Stop it first."
            )

        config = load_config(_resolve_config_path(params["config_name"]))

        import numpy as np
        rpm_points = list(np.arange(
            params["rpm_start"],
            params["rpm_end"] + params["rpm_step"] / 2,
            params["rpm_step"],
        ))
        rpm_points = [float(r) for r in rpm_points]

        sweep_id = _make_sweep_id(params)
        self._current = LiveSweepState(
            sweep_id=sweep_id,
            status="running",
            config=config,
            config_name=params["config_name"],
            rpm_points=rpm_points,
            n_cycles=params["n_cycles"],
            n_workers=params["n_workers"],
            started_at=_iso_now(),
            rpms={
                float(rpm): {"status": "queued", "rpm_index": idx}
                for idx, rpm in enumerate(rpm_points)
            },
        )

        # Broadcast a snapshot of the freshly-created sweep state to all
        # already-connected clients. Without this, any browser tab that
        # loaded BEFORE this sweep started has `sweep: null` in its store
        # and would silently drop all incoming rpm_start / cycle_done
        # events (because the store's updateRpm requires an existing
        # sweep object — see sweepStore.ts:updateRpm). The events DO
        # arrive over the wire, but they have nowhere to land. Sending
        # the snapshot here primes the store on every connected client
        # so live event handling can take over from cycle 1.
        try:
            from engine_simulator.gui.snapshot import build_snapshot
            snapshot_msg = build_snapshot(self._current, self._sweeps_dir)
            await self._broadcast_fn(snapshot_msg)
        except Exception:
            # A broadcast failure here (no clients, network error, etc.)
            # must NOT block the sweep from starting.
            pass

        from engine_simulator.gui.gui_event_consumer import GUIEventConsumer
        self._consumer = GUIEventConsumer(self._loop)
        self._drain_task = asyncio.create_task(self._drain_events())
        self._sweep_task = asyncio.create_task(
            self._run_sweep_in_thread(params)
        )

        return sweep_id

    async def stop_sweep(self):
        """Cancel a running sweep. Idempotent."""
        if self._current is None or self._current.status != "running":
            return
        if self._sweep_task is not None and not self._sweep_task.done():
            self._sweep_task.cancel()
            try:
                await self._sweep_task
            except asyncio.CancelledError:
                pass
