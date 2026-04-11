"""ParametricEventConsumer — bridges inner-sweep events onto the parametric channel.

Wraps the event stream from the underlying ParallelSweepRunner and
re-emits each event as a parametric_* WebSocket message tagged with the
current parameter_value. The inner sweep stays completely unaware it's
running inside a parametric study.
"""

from __future__ import annotations

import asyncio
import math
from typing import Callable

from engine_simulator.gui.persistence import _coerce_jsonable
from engine_simulator.simulation.parallel_sweep import (
    ConvergedEvent,
    CycleDoneEvent,
    EventConsumer,
    ProgressEvent,
    RPMDoneEvent,
    RPMErrorEvent,
    RPMStartEvent,
)


def _safe_float(v):
    """Coerce non-finite floats to None so JSON stays valid."""
    if v is None:
        return None
    try:
        return v if math.isfinite(v) else None
    except TypeError:
        return None


class ParametricEventConsumer(EventConsumer):
    """Implements the EventConsumer protocol and re-broadcasts events
    onto the parametric WebSocket channel.

    Call sites run in the parallel-sweep pump thread (not the asyncio
    loop), so we use `asyncio.run_coroutine_threadsafe` to schedule the
    broadcast back onto the event loop.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        broadcast_fn: Callable,
        study_id: str,
        parameter_value: float,
    ):
        self._loop = loop
        self._broadcast = broadcast_fn
        self._study_id = study_id
        self._parameter_value = parameter_value

    def _dispatch(self, msg: dict) -> None:
        """Schedule an async broadcast from any thread."""
        msg.setdefault("channel", "parametric")
        msg.setdefault("study_id", self._study_id)
        msg.setdefault("parameter_value", self._parameter_value)
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(msg), self._loop)
        except RuntimeError:
            # Loop closed; silently drop.
            pass

    def handle(self, event: ProgressEvent) -> None:
        if isinstance(event, RPMStartEvent):
            self._dispatch({
                "type": "parametric_rpm_start",
                "rpm": event.rpm,
                "rpm_index": event.rpm_index,
                "n_cycles_target": event.n_cycles_target,
                "ts": event.ts,
            })
        elif isinstance(event, CycleDoneEvent):
            self._dispatch({
                "type": "parametric_rpm_cycle",
                "rpm": event.rpm,
                "cycle": event.cycle,
                "delta": _safe_float(event.delta),
                "step_count": event.step_count,
                "elapsed": event.elapsed,
                "ts": event.ts,
            })
        elif isinstance(event, ConvergedEvent):
            self._dispatch({
                "type": "parametric_rpm_converged",
                "rpm": event.rpm,
                "cycle": event.cycle,
                "ts": event.ts,
            })
        elif isinstance(event, RPMDoneEvent):
            self._dispatch({
                "type": "parametric_rpm_done",
                "rpm": event.rpm,
                "perf": _coerce_jsonable(event.perf),
                "elapsed": event.elapsed,
                "step_count": event.step_count,
                "converged": event.converged,
                "ts": event.ts,
            })
        elif isinstance(event, RPMErrorEvent):
            self._dispatch({
                "type": "parametric_rpm_error",
                "rpm": event.rpm,
                "error_type": event.error_type,
                "error_msg": event.error_msg,
                "traceback": event.traceback,
                "ts": event.ts,
            })

    def close(self) -> None:
        pass
