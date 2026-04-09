"""Parallel RPM sweep — process-pool runner with structured progress events.

Each event is a frozen, picklable dataclass carrying `rpm` so consumers
(CLI today, GUI tomorrow) can route it. Events flow from worker processes
through a multiprocessing.Queue to a daemon thread in the parent, which
dispatches them to a pluggable EventConsumer.

Math is intentionally NOT in this file — it lives in moc_solver.py and
the orchestrator's run_single_rpm. This file is pure plumbing.
"""

from __future__ import annotations

import multiprocessing
import os
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from queue import Empty
from typing import Optional, Protocol, Union


@dataclass(frozen=True)
class RPMStartEvent:
    """Emitted by a worker right after _reinitialize, before the time-step loop."""
    rpm: float
    rpm_index: int          # position in rpm_points (0..len-1), stable per RPM
    n_cycles_target: int
    ts: float               # time.monotonic() in the worker


@dataclass(frozen=True)
class CycleDoneEvent:
    """Emitted at every cycle boundary inside run_single_rpm."""
    rpm: float
    cycle: int              # 1-indexed cycle that just finished
    delta: float            # convergence.max_relative_change()
    p_ivc: tuple            # tuple[float, ...] of per-cylinder p_at_IVC
    step_count: int         # cumulative steps so far this RPM
    elapsed: float          # wall-clock seconds since RPMStartEvent
    ts: float


@dataclass(frozen=True)
class ConvergedEvent:
    """Emitted when convergence is detected at a cycle boundary."""
    rpm: float
    cycle: int
    ts: float


@dataclass(frozen=True)
class RPMDoneEvent:
    """Emitted after run_single_rpm returns successfully."""
    rpm: float
    perf: dict              # the perf dict run_single_rpm returns
    elapsed: float
    step_count: int
    converged: bool
    ts: float


@dataclass(frozen=True)
class RPMErrorEvent:
    """Emitted if a worker raises an exception inside run_single_rpm."""
    rpm: float
    error_type: str
    error_msg: str
    traceback: str
    ts: float


# Union type alias for type hints
ProgressEvent = Union[
    RPMStartEvent, CycleDoneEvent, ConvergedEvent, RPMDoneEvent, RPMErrorEvent
]


class EventConsumer(Protocol):
    """Consumers receive every progress event in dispatch order.

    The CLI implementation (CLIEventConsumer below) prints tagged lines.
    A future GUI implementation will update on-screen panels.
    """

    def handle(self, event: ProgressEvent) -> None: ...
    def close(self) -> None: ...


class CLIEventConsumer:
    """Default event consumer for command-line use.

    Prints tagged lines to stdout, one per event. With verbose=True
    (the default), every cycle event is shown, giving a live firehose
    of progress from all running workers. With verbose=False, only
    start/done/converged/error events are shown.
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def handle(self, event: ProgressEvent) -> None:
        # Tag is right-aligned to 5 cols so 6000 / 13000 line up nicely
        tag = f"[{event.rpm:5.0f} RPM]"

        if isinstance(event, RPMStartEvent):
            print(f"{tag} start (rpm_idx {event.rpm_index})", flush=True)

        elif isinstance(event, CycleDoneEvent):
            if not self.verbose:
                return
            print(
                f"{tag} cycle {event.cycle}  "
                f"delta={event.delta:.4f}  steps={event.step_count}",
                flush=True,
            )

        elif isinstance(event, ConvergedEvent):
            print(f"{tag} [converged] at cycle {event.cycle}", flush=True)

        elif isinstance(event, RPMDoneEvent):
            p = event.perf
            print(
                f"{tag} DONE  "
                f"P_brk={p['brake_power_hp']:.1f} hp  "
                f"T_brk={p['brake_torque_Nm']:.1f} Nm  "
                f"VE_atm={p['volumetric_efficiency_atm'] * 100:.1f}%  "
                f"({event.elapsed:.1f}s, {event.step_count} steps)",
                flush=True,
            )

        elif isinstance(event, RPMErrorEvent):
            print(
                f"{tag} ERROR  {event.error_type}: {event.error_msg}",
                flush=True,
            )
            print(event.traceback, flush=True)

    def close(self) -> None:
        # Nothing to flush — every print is already flushed.
        pass


def _run_one_rpm(
    config,                          # EngineConfig (picklable dataclass)
    rpm: float,
    n_cycles: int,
    queue,                           # multiprocessing.Queue
    rpm_index: int,
):
    """Worker entry point for ParallelSweepRunner.

    Builds a fresh SimulationOrchestrator from the config, runs one RPM
    with an event-emitting callback, and returns (rpm, perf, results).

    All progress reporting flows through `queue` (small events). The big
    SimulationResults payload comes back via the function return value
    (i.e. through ProcessPoolExecutor's result pipe), which is faster
    and avoids overloading the queue.

    Must be a top-level function so it pickles for spawn-mode workers.
    """
    import time
    import traceback

    # Imports happen inside the function to keep the module-level import
    # graph free of circular references (orchestrator imports parallel_sweep
    # for event types, parallel_sweep imports orchestrator here for the
    # solver — keeping this import lazy avoids the cycle).
    from engine_simulator.simulation.orchestrator import SimulationOrchestrator

    t_start = time.monotonic()
    try:
        sim = SimulationOrchestrator(config)

        def emit(event):
            # Re-tag RPMStartEvent with the correct rpm_index. The orchestrator
            # emits with rpm_index=0 because it doesn't know its position in
            # the sweep; we patch it here in the worker that does.
            if isinstance(event, RPMStartEvent):
                event = RPMStartEvent(
                    rpm=event.rpm,
                    rpm_index=rpm_index,
                    n_cycles_target=event.n_cycles_target,
                    ts=event.ts,
                )
            queue.put(event)

        perf = sim.run_single_rpm(
            rpm=rpm,
            n_cycles=n_cycles,
            verbose=False,           # workers never use the print path
            event_callback=emit,
        )

        return (float(rpm), perf, sim.results)

    except Exception as exc:
        queue.put(RPMErrorEvent(
            rpm=float(rpm),
            error_type=type(exc).__name__,
            error_msg=str(exc),
            traceback=traceback.format_exc(),
            ts=time.monotonic(),
        ))
        raise


class ParallelSweepRunner:
    """Parent-side coordinator for parallel RPM sweeps.

    Owns the process pool, the event queue, and a daemon thread that
    drains the queue and forwards events to the configured consumer.

    Usage:
        runner = ParallelSweepRunner(config, n_workers=8, consumer=CLIEventConsumer())
        sweep_results, results_by_rpm = runner.run(rpm_points, n_cycles=12)
    """

    def __init__(
        self,
        config,                                       # EngineConfig
        n_workers: Optional[int] = None,
        consumer: Optional["EventConsumer"] = None,
        worker_fn=None,                               # for tests; defaults to _run_one_rpm
        executor_factory=None,                        # for tests; defaults to ProcessPoolExecutor
    ):
        self.config = config
        self.n_workers = n_workers                    # resolved in .run() if None
        self.consumer = consumer or CLIEventConsumer(verbose=True)
        # Indirection lets tests inject a stub. Production code uses
        # the module-level _run_one_rpm.
        self._worker_fn = worker_fn if worker_fn is not None else _run_one_rpm
        # Indirection lets tests inject a ThreadPoolExecutor (in-process)
        # so they don't need to pickle stub functions across processes.
        # Production code uses the default _make_process_pool factory below.
        self._executor_factory = executor_factory or self._make_process_pool

    @staticmethod
    def _make_process_pool(max_workers, ctx):
        return ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx)

    def _resolve_n_workers(self, n_rpm_points: int) -> int:
        if self.n_workers is not None:
            # Explicit user override, but still cap at len(rpm_points)
            # so we don't spawn workers that would have no work to do.
            return max(1, min(self.n_workers, n_rpm_points))
        cpu = os.cpu_count() or 1
        return max(1, min(cpu, n_rpm_points))

    def _pump_events(self, queue, done_event):
        """Daemon thread body: drain `queue` and dispatch to consumer.

        Polls with a short timeout so it can notice `done_event` being set.
        """
        while True:
            try:
                event = queue.get(timeout=0.1)
            except Empty:
                if done_event.is_set():
                    # Drain anything still queued before exiting.
                    while True:
                        try:
                            event = queue.get_nowait()
                        except Empty:
                            return
                        try:
                            self.consumer.handle(event)
                        except Exception:
                            # Consumer errors must not kill the sweep.
                            pass
                continue
            try:
                self.consumer.handle(event)
            except Exception:
                pass

    def run(self, rpm_points, n_cycles: int):
        """Run all RPM points in parallel and return (sweep_results, results_by_rpm).

        sweep_results is a list of perf dicts in the same order as rpm_points.
        results_by_rpm is a dict mapping float(rpm) -> SimulationResults.
        """
        rpm_points = list(rpm_points)
        if not rpm_points:
            self.consumer.close()
            return [], {}

        n_workers = self._resolve_n_workers(len(rpm_points))

        ctx = multiprocessing.get_context("spawn")

        # IMPORTANT: under spawn mode, raw ctx.Queue() instances CAN'T be
        # passed as pool.submit() arguments — they're only inheritable via
        # the parent-child fork relationship and refuse to pickle. We use
        # a Manager-backed queue instead, which provides a picklable proxy
        # object that any worker can use to send events back.
        manager = ctx.Manager()
        queue = manager.Queue()

        done_event = threading.Event()
        pump_thread = threading.Thread(
            target=self._pump_events,
            args=(queue, done_event),
            daemon=True,
        )
        pump_thread.start()

        sweep_results = [None] * len(rpm_points)
        results_by_rpm: dict = {}

        try:
            with self._executor_factory(n_workers, ctx) as pool:
                # Submission order is RPM order; future->index map
                # lets us write results back into the right slot.
                futures = {
                    pool.submit(
                        self._worker_fn,
                        self.config,
                        float(rpm),
                        n_cycles,
                        queue,
                        idx,
                    ): idx
                    for idx, rpm in enumerate(rpm_points)
                }

                for future in as_completed(futures):
                    idx = futures[future]
                    rpm, perf, results = future.result()  # may raise
                    sweep_results[idx] = perf
                    results_by_rpm[float(rpm)] = results
        finally:
            # Tell the pump to drain and exit, regardless of how we left
            # the with-block (success or exception).
            done_event.set()
            pump_thread.join(timeout=2.0)
            # Manager-backed queues don't have close()/join_thread() — the
            # Manager process is shut down via manager.shutdown() instead.
            try:
                manager.shutdown()
            except Exception:
                pass
            self.consumer.close()

        return sweep_results, results_by_rpm
