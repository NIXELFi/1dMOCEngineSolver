# Parallel RPM Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parallelize the engine simulator's RPM sweep across multiple processes (one RPM per worker), with bit-for-bit identical numerical results to the existing sequential path and a structured progress-event stream that a future GUI can consume.

**Architecture:** Process pool (`concurrent.futures.ProcessPoolExecutor` with `mp_context="spawn"`) at the RPM level. Each worker builds its own `SimulationOrchestrator`, runs `run_single_rpm`, and emits structured events via a shared `multiprocessing.Queue`. Parent process drains the queue from a daemon thread and dispatches events to a pluggable `EventConsumer` (CLI today, GUI tomorrow). The `gas_dynamics/`, `engine/`, `boundaries/`, and `simulation/plenum.py|convergence.py|engine_cycle.py` files are NOT touched — only orchestration plumbing changes.

**Tech Stack:** Python 3.9+, NumPy, pytest. Standard-library `concurrent.futures`, `multiprocessing`, `threading`. No new third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-04-08-parallel-rpm-sweep-design.md`

**Note on git:** This project is not currently a git repository, so the "Save progress" steps below show the git commands you would run if it were. If git is not initialized, just check that no other tests have regressed before moving to the next task.

---

## File Structure

**New files (5):**

| Path | Responsibility |
|---|---|
| `engine_simulator/simulation/parallel_sweep.py` | Event dataclasses, `EventConsumer` protocol, `CLIEventConsumer`, `_run_one_rpm` worker entry, `ParallelSweepRunner` |
| `tests/test_event_consumer.py` | `CLIEventConsumer` formatting tests with synthetic events (no solver) |
| `tests/test_orchestrator_event_callback.py` | `run_single_rpm` event_callback emission tests (uses real solver, very short run) |
| `tests/test_parallel_sweep_runner.py` | `ParallelSweepRunner` plumbing tests with stub worker function |
| `tests/test_parallel_sweep_equivalence.py` | Layer 1 (perf-dict) and Layer 2 (`SimulationResults`) numerical equivalence between sequential and parallel paths |

**Modified files (2):**

| Path | Changes |
|---|---|
| `engine_simulator/simulation/orchestrator.py` | Add `event_callback` param to `run_single_rpm`; add `results_by_rpm`, `_last_step_count`, `_last_converged` instance attributes; add `n_workers`, `consumer` params to `run_rpm_sweep`; extract `_print_sweep_summary` |
| `engine_simulator/main.py` | Add `--workers <int>` and `--quiet` CLI flags, thread through to `run_rpm_sweep` |

**Files explicitly NOT touched:**

- `engine_simulator/gas_dynamics/moc_solver.py`, `pipe.py`, `cfl.py`, `gas_properties.py`
- `engine_simulator/engine/cylinder.py`, `valve.py`, `kinematics.py`
- `engine_simulator/boundaries/*`
- `engine_simulator/simulation/plenum.py`, `convergence.py`, `engine_cycle.py`
- `engine_simulator/postprocessing/results.py` (`SimulationResults` is already picklable)
- `_run_sweep.py`, `_run_sweep_fast.py`, and other top-level driver scripts

---

## Phase A: Event Types & CLIEventConsumer

This phase introduces `parallel_sweep.py` with just the event dataclasses and the CLI consumer. No solver, no orchestrator changes, no multiprocessing yet. End of phase: `pytest tests/test_event_consumer.py` passes; the rest of the codebase is unchanged.

### Task 1: Create event dataclasses

**Files:**
- Create: `engine_simulator/simulation/parallel_sweep.py`

- [ ] **Step 1: Create the new file with event dataclasses and the EventConsumer protocol**

```python
# engine_simulator/simulation/parallel_sweep.py
"""Parallel RPM sweep — process-pool runner with structured progress events.

Each event is a frozen, picklable dataclass carrying `rpm` so consumers
(CLI today, GUI tomorrow) can route it. Events flow from worker processes
through a multiprocessing.Queue to a daemon thread in the parent, which
dispatches them to a pluggable EventConsumer.

Math is intentionally NOT in this file — it lives in moc_solver.py and
the orchestrator's run_single_rpm. This file is pure plumbing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Union


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
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `cd  && .venv/bin/python -c "from engine_simulator.simulation.parallel_sweep import RPMStartEvent, CycleDoneEvent, ConvergedEvent, RPMDoneEvent, RPMErrorEvent, EventConsumer; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Save progress (skip if not using git)**

```bash
git add engine_simulator/simulation/parallel_sweep.py
git commit -m "feat(parallel): add progress event dataclasses for RPM sweep"
```

---

### Task 2: Write failing tests for CLIEventConsumer formatting

**Files:**
- Create: `tests/test_event_consumer.py`

- [ ] **Step 1: Write the test file with synthetic events and expected output**

```python
# tests/test_event_consumer.py
"""CLIEventConsumer formatting tests.

These pass synthetic events into the consumer and assert the captured
stdout matches inline expected strings. They do NOT touch the solver,
so they run in milliseconds.
"""

import io
from contextlib import redirect_stdout

import pytest

from engine_simulator.simulation.parallel_sweep import (
    CLIEventConsumer,
    ConvergedEvent,
    CycleDoneEvent,
    RPMDoneEvent,
    RPMErrorEvent,
    RPMStartEvent,
)


def _capture(consumer_action):
    """Run consumer_action() with stdout captured, return captured text."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        consumer_action()
    return buf.getvalue()


class TestCLIEventConsumer:
    def test_rpm_start_format(self):
        consumer = CLIEventConsumer(verbose=True)
        event = RPMStartEvent(
            rpm=8000.0, rpm_index=1, n_cycles_target=12, ts=0.0
        )
        out = _capture(lambda: consumer.handle(event))
        assert out == "[ 8000 RPM] start (rpm_idx 1)\n"

    def test_cycle_done_format(self):
        consumer = CLIEventConsumer(verbose=True)
        event = CycleDoneEvent(
            rpm=10000.0, cycle=2, delta=0.0341,
            p_ivc=(95000.0, 96000.0, 95500.0, 96100.0),
            step_count=2487, elapsed=4.2, ts=0.0,
        )
        out = _capture(lambda: consumer.handle(event))
        assert out == "[10000 RPM] cycle 2  delta=0.0341  steps=2487\n"

    def test_converged_format(self):
        consumer = CLIEventConsumer(verbose=True)
        event = ConvergedEvent(rpm=8000.0, cycle=4, ts=0.0)
        out = _capture(lambda: consumer.handle(event))
        assert out == "[ 8000 RPM] [converged] at cycle 4\n"

    def test_rpm_done_format(self):
        consumer = CLIEventConsumer(verbose=True)
        perf = {
            "brake_power_hp": 68.2,
            "brake_torque_Nm": 51.3,
            "volumetric_efficiency_atm": 0.924,
        }
        event = RPMDoneEvent(
            rpm=8000.0, perf=perf, elapsed=11.2,
            step_count=4523, converged=True, ts=0.0,
        )
        out = _capture(lambda: consumer.handle(event))
        assert out == (
            "[ 8000 RPM] DONE  P_brk=68.2 hp  T_brk=51.3 Nm  "
            "VE_atm=92.4%  (11.2s, 4523 steps)\n"
        )

    def test_rpm_error_format(self):
        consumer = CLIEventConsumer(verbose=True)
        event = RPMErrorEvent(
            rpm=9000.0, error_type="ValueError",
            error_msg="bad config", traceback="Traceback...\n", ts=0.0,
        )
        out = _capture(lambda: consumer.handle(event))
        # The first line should always show the rpm tag and error type+msg
        assert "[ 9000 RPM] ERROR  ValueError: bad config" in out

    def test_quiet_mode_suppresses_cycle_events(self):
        consumer = CLIEventConsumer(verbose=False)
        cycle_event = CycleDoneEvent(
            rpm=8000.0, cycle=1, delta=0.05, p_ivc=(),
            step_count=100, elapsed=1.0, ts=0.0,
        )
        out = _capture(lambda: consumer.handle(cycle_event))
        assert out == ""  # quiet mode swallows cycle events

    def test_quiet_mode_still_shows_done(self):
        consumer = CLIEventConsumer(verbose=False)
        done = RPMDoneEvent(
            rpm=8000.0, perf={"brake_power_hp": 68.2, "brake_torque_Nm": 51.3,
                              "volumetric_efficiency_atm": 0.924},
            elapsed=11.2, step_count=4523, converged=True, ts=0.0,
        )
        out = _capture(lambda: consumer.handle(done))
        assert out != ""  # quiet still shows done lines

    def test_close_is_callable(self):
        consumer = CLIEventConsumer(verbose=True)
        consumer.close()  # must not raise
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd  && .venv/bin/pytest tests/test_event_consumer.py -v`
Expected: ImportError or AttributeError because `CLIEventConsumer` does not exist yet.

---

### Task 3: Implement CLIEventConsumer to make tests pass

**Files:**
- Modify: `engine_simulator/simulation/parallel_sweep.py` (append to end)

- [ ] **Step 1: Append CLIEventConsumer to parallel_sweep.py**

Add this code at the end of `engine_simulator/simulation/parallel_sweep.py`:

```python


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
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `cd  && .venv/bin/pytest tests/test_event_consumer.py -v`
Expected: All 8 tests pass.

- [ ] **Step 3: Save progress**

```bash
git add engine_simulator/simulation/parallel_sweep.py tests/test_event_consumer.py
git commit -m "feat(parallel): add CLIEventConsumer with formatting tests"
```

---

## Phase B: Orchestrator event_callback Hook

This phase adds the `event_callback` parameter to `run_single_rpm` and emits events at the same code points where prints currently happen. With `event_callback=None` (the default), behavior is byte-identical to today.

### Task 4: Write failing test for event_callback emission

**Files:**
- Create: `tests/test_orchestrator_event_callback.py`

- [ ] **Step 1: Write the test file**

```python
# tests/test_orchestrator_event_callback.py
"""Verify run_single_rpm emits events at the same code points as prints.

These tests run a real solver at one RPM with a very short cycle count
so they're fast (~5-10 seconds). They do NOT validate numerical results
— that's the equivalence test's job. They only validate the event stream.
"""

from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator
from engine_simulator.simulation.parallel_sweep import (
    ConvergedEvent,
    CycleDoneEvent,
    RPMDoneEvent,
    RPMStartEvent,
)


class TestEventCallback:
    def _run(self, n_cycles=4):
        config = EngineConfig()
        sim = SimulationOrchestrator(config)
        events = []
        sim.run_single_rpm(
            rpm=10000.0,
            n_cycles=n_cycles,
            verbose=False,
            event_callback=events.append,
        )
        return events, sim

    def test_emits_rpm_start_first(self):
        events, _sim = self._run()
        assert len(events) >= 1
        assert isinstance(events[0], RPMStartEvent)
        assert events[0].rpm == 10000.0
        assert events[0].n_cycles_target == 4

    def test_emits_rpm_done_last(self):
        events, _sim = self._run()
        assert isinstance(events[-1], RPMDoneEvent)
        assert events[-1].rpm == 10000.0
        # perf dict is the same shape run_single_rpm returns
        assert "brake_power_hp" in events[-1].perf
        assert "indicated_power_hp" in events[-1].perf
        assert "volumetric_efficiency_atm" in events[-1].perf

    def test_emits_one_cycle_done_per_cycle_boundary(self):
        events, _sim = self._run(n_cycles=4)
        cycle_events = [e for e in events if isinstance(e, CycleDoneEvent)]
        # We expect at least one per cycle boundary that the loop reaches.
        # The exact number depends on convergence; assert >= 1 and that
        # cycle numbers are monotonically increasing.
        assert len(cycle_events) >= 1
        cycles_seen = [e.cycle for e in cycle_events]
        assert cycles_seen == sorted(cycles_seen)

    def test_cycle_event_payload_is_consistent(self):
        events, _sim = self._run()
        cycle_events = [e for e in events if isinstance(e, CycleDoneEvent)]
        for e in cycle_events:
            assert e.rpm == 10000.0
            assert isinstance(e.delta, float)
            assert e.delta >= 0.0
            assert e.step_count > 0
            assert e.elapsed >= 0.0
            assert isinstance(e.p_ivc, tuple)
            assert len(e.p_ivc) == 4   # 4 cylinders for the CBR600RR config

    def test_converged_event_emitted_when_convergence_fires(self):
        # Run with enough cycles that convergence has a chance to fire
        events, _sim = self._run(n_cycles=12)
        # We can't guarantee convergence at exactly 12 cycles for arbitrary
        # configs, but for the default 10000 RPM it should converge.
        # If it does, the event should appear after at least one CycleDoneEvent.
        converged = [e for e in events if isinstance(e, ConvergedEvent)]
        if converged:
            first_converged_idx = events.index(converged[0])
            cycle_events_before = [
                e for e in events[:first_converged_idx]
                if isinstance(e, CycleDoneEvent)
            ]
            assert len(cycle_events_before) >= 1

    def test_callback_default_is_none_does_not_break_old_path(self):
        """Without an event_callback, run_single_rpm must work exactly as before."""
        config = EngineConfig()
        sim = SimulationOrchestrator(config)
        # No event_callback param at all — old call signature
        perf = sim.run_single_rpm(rpm=10000.0, n_cycles=4, verbose=False)
        assert "brake_power_hp" in perf

    def test_last_step_count_and_converged_attributes_set(self):
        _events, sim = self._run()
        assert sim._last_step_count > 0
        assert isinstance(sim._last_converged, bool)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd  && .venv/bin/pytest tests/test_orchestrator_event_callback.py -v`
Expected: TypeError because `run_single_rpm` does not yet accept `event_callback`. May also fail with AttributeError on `_last_step_count`.

---

### Task 5: Add event_callback parameter and emission points to run_single_rpm

**Files:**
- Modify: `engine_simulator/simulation/orchestrator.py`

- [ ] **Step 1: Add new instance attributes to `__init__`**

Find this block in `engine_simulator/simulation/orchestrator.py` (around line 41-51):

```python
    def __init__(self, config: EngineConfig):
        self.config = config
        self.gamma = GAMMA_REF

        # Build all simulation components
        self._build_pipes()
        self._build_cylinders()
        self._build_plenum()
        self._build_boundaries()

        self.results = SimulationResults()
```

Replace the last line with:

```python
        self.results = SimulationResults()

        # Per-RPM results aggregation (populated by run_rpm_sweep, both
        # sequential and parallel paths). Keyed by float(rpm).
        self.results_by_rpm: dict = {}

        # Set inside run_single_rpm so that workers in parallel mode can
        # report total step count and convergence status without re-deriving.
        self._last_step_count: int = 0
        self._last_converged: bool = False
```

- [ ] **Step 2: Add the imports needed for event types and callable typing**

Find this block at the top of the file (around line 1-28):

```python
"""Main simulation orchestrator: time-stepping loop coupling all subsystems."""

from __future__ import annotations

import time
from typing import Optional

import numpy as np
```

Replace it with:

```python
"""Main simulation orchestrator: time-stepping loop coupling all subsystems."""

from __future__ import annotations

import time
from typing import Callable, Optional

import numpy as np

from engine_simulator.simulation.parallel_sweep import (
    ConvergedEvent,
    CycleDoneEvent,
    ProgressEvent,
    RPMDoneEvent,
    RPMStartEvent,
)
```

- [ ] **Step 3: Add the event_callback parameter to run_single_rpm**

Find this signature in `orchestrator.py` (around line 211-217):

```python
    def run_single_rpm(
        self,
        rpm: float,
        n_cycles: int = 5,
        record_last_cycle: bool = True,
        verbose: bool = True,
    ) -> dict:
```

Replace it with:

```python
    def run_single_rpm(
        self,
        rpm: float,
        n_cycles: int = 5,
        record_last_cycle: bool = True,
        verbose: bool = True,
        event_callback: Optional[Callable[[ProgressEvent], None]] = None,
    ) -> dict:
```

- [ ] **Step 4: Emit RPMStartEvent at the top of the run loop**

Find this block in `run_single_rpm` (around line 240-247):

```python
        if verbose:
            print(f"  Running {rpm:.0f} RPM...", end="", flush=True)

        t_start = time.time()
        step_count = 0

        mdot_restrictor = 0.0
```

Replace it with:

```python
        if verbose:
            print(f"  Running {rpm:.0f} RPM...", end="", flush=True)

        t_start = time.time()
        step_count = 0

        mdot_restrictor = 0.0

        if event_callback is not None:
            event_callback(RPMStartEvent(
                rpm=float(rpm),
                rpm_index=0,           # not known here; set by ParallelSweepRunner via _run_one_rpm
                n_cycles_target=n_cycles,
                ts=time.monotonic(),
            ))
```

- [ ] **Step 5: Emit CycleDoneEvent at the cycle boundary**

Find this block in `run_single_rpm` (around line 322-330):

```python
            # Check for cycle boundary
            new_cycle = int(theta / 720.0)
            if new_cycle > current_cycle:
                # Record convergence data
                p_ivc_values = [cyl.p_at_IVC for cyl in self.cylinders]
                convergence.record_cycle(p_ivc_values)

                if verbose:
                    change = convergence.max_relative_change()
                    print(f" cycle {new_cycle} (delta={change:.4f})", end="", flush=True)
```

Replace it with:

```python
            # Check for cycle boundary
            new_cycle = int(theta / 720.0)
            if new_cycle > current_cycle:
                # Record convergence data
                p_ivc_values = [cyl.p_at_IVC for cyl in self.cylinders]
                convergence.record_cycle(p_ivc_values)

                change = convergence.max_relative_change()
                if verbose:
                    print(f" cycle {new_cycle} (delta={change:.4f})", end="", flush=True)
                if event_callback is not None:
                    event_callback(CycleDoneEvent(
                        rpm=float(rpm),
                        cycle=new_cycle,
                        delta=float(change),
                        p_ivc=tuple(float(p) for p in p_ivc_values),
                        step_count=step_count,
                        elapsed=time.time() - t_start,
                        ts=time.monotonic(),
                    ))
```

- [ ] **Step 6: Emit ConvergedEvent in both convergence branches**

Find this block in `run_single_rpm` (around line 343-347):

```python
                if new_cycle >= n_cycles:
                    if verbose and convergence.is_converged():
                        print(" [converged-final]", end="")
                    current_cycle = new_cycle
                    break
```

Replace it with:

```python
                if new_cycle >= n_cycles:
                    if convergence.is_converged():
                        if verbose:
                            print(" [converged-final]", end="")
                        if event_callback is not None:
                            event_callback(ConvergedEvent(
                                rpm=float(rpm),
                                cycle=new_cycle,
                                ts=time.monotonic(),
                            ))
                    current_cycle = new_cycle
                    break
```

Then find this block (a few lines later, around line 351-361):

```python
                # Convergence: schedule one more cycle with recording, then break.
                # Only do this if there is room for the bonus cycle to actually run.
                if convergence.is_converged() and new_cycle >= 3:
                    if verbose:
                        print(" [converged]", end="")
                    recording_cycle = True
                    # Reset accumulators so the bonus cycle's totals reflect that cycle alone
                    for cyl in self.cylinders:
                        cyl.m_intake_total = 0.0
                        cyl.m_exhaust_total = 0.0
                        cyl.work_cycle = 0.0
                    current_cycle = new_cycle
                    continue
```

Replace it with:

```python
                # Convergence: schedule one more cycle with recording, then break.
                # Only do this if there is room for the bonus cycle to actually run.
                if convergence.is_converged() and new_cycle >= 3:
                    if verbose:
                        print(" [converged]", end="")
                    if event_callback is not None:
                        event_callback(ConvergedEvent(
                            rpm=float(rpm),
                            cycle=new_cycle,
                            ts=time.monotonic(),
                        ))
                    recording_cycle = True
                    # Reset accumulators so the bonus cycle's totals reflect that cycle alone
                    for cyl in self.cylinders:
                        cyl.m_intake_total = 0.0
                        cyl.m_exhaust_total = 0.0
                        cyl.work_cycle = 0.0
                    current_cycle = new_cycle
                    continue
```

- [ ] **Step 7: Set _last_step_count and _last_converged, then emit RPMDoneEvent at the end**

Find this block at the bottom of `run_single_rpm` (around line 371-376):

```python
        elapsed = time.time() - t_start
        if verbose:
            print(f" ({elapsed:.1f}s, {step_count} steps)")

        # Compute performance metrics
        return self._compute_performance(rpm)
```

Replace it with:

```python
        elapsed = time.time() - t_start
        if verbose:
            print(f" ({elapsed:.1f}s, {step_count} steps)")

        # Stash these so workers can attach them to RPMDoneEvent without
        # re-deriving from instance state.
        self._last_step_count = step_count
        self._last_converged = bool(convergence.is_converged())

        # Compute performance metrics
        perf = self._compute_performance(rpm)

        if event_callback is not None:
            event_callback(RPMDoneEvent(
                rpm=float(rpm),
                perf=perf,
                elapsed=elapsed,
                step_count=step_count,
                converged=self._last_converged,
                ts=time.monotonic(),
            ))

        return perf
```

- [ ] **Step 8: Run the event_callback tests to verify they pass**

Run: `cd  && .venv/bin/pytest tests/test_orchestrator_event_callback.py -v`
Expected: All 7 tests pass.

- [ ] **Step 9: Run the existing test suite to verify no math regression**

Run: `cd  && .venv/bin/pytest tests/ -v --ignore=tests/test_event_consumer.py --ignore=tests/test_orchestrator_event_callback.py`
Expected: All previously-passing tests still pass. Pay attention to `test_moc.py`, `test_boundaries.py`, `test_cylinder.py`, `test_drivetrain.py` — none should regress.

- [ ] **Step 10: Save progress**

```bash
git add engine_simulator/simulation/orchestrator.py tests/test_orchestrator_event_callback.py
git commit -m "feat(parallel): add event_callback hook to run_single_rpm"
```

---

## Phase C: results_by_rpm Collection in Sequential Path

This phase makes the sequential `run_rpm_sweep` populate `self.results_by_rpm` with one `SimulationResults` per RPM, so the parallel path and the sequential path return the same data shape. The change is one new line; the existing flow is otherwise unchanged.

### Task 6: Backfill results_by_rpm in the sequential sweep loop

**Files:**
- Modify: `engine_simulator/simulation/orchestrator.py`

- [ ] **Step 1: Update the sequential sweep loop to retain per-RPM results**

Find this block in `run_rpm_sweep` (around line 483-486):

```python
        for rpm in rpm_points:
            self.results = SimulationResults()  # fresh for each RPM
            perf = self.run_single_rpm(rpm, n_cycles=n_cycles, verbose=verbose)
            sweep_results.append(perf)
```

Replace it with:

```python
        for rpm in rpm_points:
            self.results = SimulationResults()  # fresh for each RPM
            perf = self.run_single_rpm(rpm, n_cycles=n_cycles, verbose=verbose)
            sweep_results.append(perf)
            # Retain a per-RPM copy so callers (and the future GUI) can
            # access the recorded last-cycle data for every RPM, not just
            # the last one.
            self.results_by_rpm[float(rpm)] = self.results
```

- [ ] **Step 2: Write a quick smoke test that the dict is populated**

Append to `tests/test_orchestrator_event_callback.py`:

```python


class TestResultsByRpm:
    def test_sequential_sweep_populates_results_by_rpm(self):
        """A short sequential sweep populates results_by_rpm with one
        SimulationResults per RPM, keyed by float(rpm)."""
        from engine_simulator.config.engine_config import EngineConfig
        from engine_simulator.postprocessing.results import SimulationResults
        from engine_simulator.simulation.orchestrator import SimulationOrchestrator

        config = EngineConfig()
        sim = SimulationOrchestrator(config)
        sim.run_rpm_sweep(
            rpm_start=8000, rpm_end=10000, rpm_step=2000,
            n_cycles=4, verbose=False,
        )

        assert set(sim.results_by_rpm.keys()) == {8000.0, 10000.0}
        for rpm, results in sim.results_by_rpm.items():
            assert isinstance(results, SimulationResults)
            # The recorded last cycle should have at least some data
            assert len(results.theta_history) > 0
```

- [ ] **Step 3: Run the new test to verify it passes**

Run: `cd  && .venv/bin/pytest tests/test_orchestrator_event_callback.py::TestResultsByRpm -v`
Expected: The new test passes.

- [ ] **Step 4: Run the full test suite to verify nothing regressed**

Run: `cd  && .venv/bin/pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 5: Save progress**

```bash
git add engine_simulator/simulation/orchestrator.py tests/test_orchestrator_event_callback.py
git commit -m "feat(parallel): retain per-RPM SimulationResults in sequential sweep"
```

---

## Phase D: Extract _print_sweep_summary

A pure code move so both the sequential and parallel paths can call the same summary-table renderer.

### Task 7: Extract the summary table into a private helper

**Files:**
- Modify: `engine_simulator/simulation/orchestrator.py`

- [ ] **Step 1: Add the new private helper method**

Find the end of `run_rpm_sweep` in `orchestrator.py` (around line 488-500). It looks like:

```python
        if verbose:
            print("\n--- Performance Summary ---")
            print(f"{'RPM':>6} {'P_ind(hp)':>10} {'P_brk(hp)':>10} {'T_brk(Nm)':>10} {'VE_p(%)':>8} {'VE_a(%)':>8} {'IMEP':>6} {'BMEP':>6} {'pPlen':>6} {'Chkd':>5}")
            for r in sweep_results:
                print(
                    f"{r['rpm']:6.0f} {r['indicated_power_hp']:10.1f} "
                    f"{r['brake_power_hp']:10.1f} {r['brake_torque_Nm']:10.1f} "
                    f"{r['volumetric_efficiency_plenum']*100:8.1f} {r['volumetric_efficiency_atm']*100:8.1f} "
                    f"{r['imep_bar']:6.2f} {r['bmep_bar']:6.2f} {r['plenum_pressure_bar']:6.3f} "
                    f"{'Yes' if r['restrictor_choked'] else 'No':>5}"
                )

        return sweep_results
```

Replace it with:

```python
        if verbose:
            self._print_sweep_summary(sweep_results)

        return sweep_results

    def _print_sweep_summary(self, sweep_results: list[dict]) -> None:
        """Print the per-RPM summary table. Identical for sequential and parallel
        paths so on-screen output is byte-for-byte identical regardless of --workers.
        """
        print("\n--- Performance Summary ---")
        print(f"{'RPM':>6} {'P_ind(hp)':>10} {'P_brk(hp)':>10} {'T_brk(Nm)':>10} {'VE_p(%)':>8} {'VE_a(%)':>8} {'IMEP':>6} {'BMEP':>6} {'pPlen':>6} {'Chkd':>5}")
        for r in sweep_results:
            print(
                f"{r['rpm']:6.0f} {r['indicated_power_hp']:10.1f} "
                f"{r['brake_power_hp']:10.1f} {r['brake_torque_Nm']:10.1f} "
                f"{r['volumetric_efficiency_plenum']*100:8.1f} {r['volumetric_efficiency_atm']*100:8.1f} "
                f"{r['imep_bar']:6.2f} {r['bmep_bar']:6.2f} {r['plenum_pressure_bar']:6.3f} "
                f"{'Yes' if r['restrictor_choked'] else 'No':>5}"
            )
```

- [ ] **Step 2: Run a quick sequential sweep manually to verify the output is unchanged**

Run: `cd  && .venv/bin/python -c "
from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator
sim = SimulationOrchestrator(EngineConfig())
sim.run_rpm_sweep(rpm_start=8000, rpm_end=10000, rpm_step=2000, n_cycles=4, verbose=True)
"`
Expected: The "Performance Summary" header and table appear, formatted exactly as before.

- [ ] **Step 3: Run the full test suite to verify nothing regressed**

Run: `cd  && .venv/bin/pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 4: Save progress**

```bash
git add engine_simulator/simulation/orchestrator.py
git commit -m "refactor(orchestrator): extract _print_sweep_summary helper"
```

---

## Phase E: Worker Entry Function

Adds the top-level `_run_one_rpm` function that workers will execute. It must be top-level (not a closure or instance method) so it pickles for `spawn`.

### Task 8: Implement _run_one_rpm worker entry

**Files:**
- Modify: `engine_simulator/simulation/parallel_sweep.py`

- [ ] **Step 1: Append _run_one_rpm to parallel_sweep.py**

Add this code at the end of `engine_simulator/simulation/parallel_sweep.py`:

```python


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
```

- [ ] **Step 2: Verify the new function imports cleanly**

Run: `cd  && .venv/bin/python -c "from engine_simulator.simulation.parallel_sweep import _run_one_rpm; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Save progress**

```bash
git add engine_simulator/simulation/parallel_sweep.py
git commit -m "feat(parallel): add _run_one_rpm worker entry function"
```

---

## Phase F: ParallelSweepRunner

Adds the parent-side runner that owns the process pool, the event queue, the pump thread, and result aggregation.

### Task 9: Write failing tests for ParallelSweepRunner

**Files:**
- Create: `tests/test_parallel_sweep_runner.py`

- [ ] **Step 1: Write the test file**

```python
# tests/test_parallel_sweep_runner.py
"""ParallelSweepRunner plumbing tests.

These do NOT use the real solver. They monkey-patch the worker entry
function with a stub that returns canned data, so they're fast and
isolated from the math. The real-solver equivalence test lives in
test_parallel_sweep_equivalence.py.
"""

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from engine_simulator.simulation.parallel_sweep import (
    CLIEventConsumer,
    ConvergedEvent,
    CycleDoneEvent,
    ParallelSweepRunner,
    RPMDoneEvent,
    RPMStartEvent,
)


# Tests inject this factory so the runner uses an in-process executor
# instead of a real ProcessPoolExecutor. This sidesteps cross-process
# pickling issues for stub functions and stub result objects.
def _thread_executor_factory(max_workers, ctx):
    return ThreadPoolExecutor(max_workers=max_workers)


class _RecordingConsumer:
    def __init__(self):
        self.events = []
        self.closed = False

    def handle(self, event):
        self.events.append(event)

    def close(self):
        self.closed = True


class _FakeResults:
    """Stand-in for SimulationResults in plumbing tests.

    Module-level so it pickles cleanly across the process boundary.
    Carries an rpm_marker so the test can verify per-RPM identity.
    """
    def __init__(self, rpm):
        self.rpm_marker = float(rpm)


def _stub_run_one_rpm(config, rpm, n_cycles, queue, rpm_index):
    """Stub worker: emits a fake event sequence and returns canned results.

    Defined at module level so pickle can serialize it for spawn workers.
    """
    import time as _t
    queue.put(RPMStartEvent(
        rpm=float(rpm), rpm_index=rpm_index,
        n_cycles_target=n_cycles, ts=_t.monotonic(),
    ))
    queue.put(CycleDoneEvent(
        rpm=float(rpm), cycle=1, delta=0.05, p_ivc=(95000.0,) * 4,
        step_count=100, elapsed=0.01, ts=_t.monotonic(),
    ))
    queue.put(ConvergedEvent(rpm=float(rpm), cycle=2, ts=_t.monotonic()))
    perf = {
        "rpm": float(rpm),
        "brake_power_hp": 60.0 + rpm / 1000.0,   # rpm-dependent so we can verify ordering
        "brake_torque_Nm": 50.0,
        "volumetric_efficiency_atm": 0.9,
        "indicated_power_hp": 70.0,
    }
    queue.put(RPMDoneEvent(
        rpm=float(rpm), perf=perf, elapsed=0.02,
        step_count=200, converged=True, ts=_t.monotonic(),
    ))

    return (float(rpm), perf, _FakeResults(rpm))


def _failing_run_one_rpm(config, rpm, n_cycles, queue, rpm_index):
    raise ValueError(f"boom at {rpm}")


class TestParallelSweepRunner:
    def test_run_returns_results_in_rpm_order(self):
        consumer = _RecordingConsumer()
        runner = ParallelSweepRunner(
            config=None, n_workers=2, consumer=consumer,
            worker_fn=_stub_run_one_rpm,
            executor_factory=_thread_executor_factory,
        )
        rpm_points = [6000.0, 8000.0, 10000.0, 12000.0]
        sweep_results, results_by_rpm = runner.run(rpm_points, n_cycles=4)

        # Order matches rpm_points, NOT finish order
        assert [r["rpm"] for r in sweep_results] == rpm_points

    def test_results_by_rpm_keyed_correctly(self):
        consumer = _RecordingConsumer()
        runner = ParallelSweepRunner(
            config=None, n_workers=2, consumer=consumer,
            worker_fn=_stub_run_one_rpm,
            executor_factory=_thread_executor_factory,
        )
        rpm_points = [6000.0, 10000.0]
        _sweep, results_by_rpm = runner.run(rpm_points, n_cycles=4)

        assert set(results_by_rpm.keys()) == {6000.0, 10000.0}
        # Per-RPM identity preserved through pickle
        assert results_by_rpm[6000.0].rpm_marker == 6000.0
        assert results_by_rpm[10000.0].rpm_marker == 10000.0

    def test_consumer_receives_all_event_types(self):
        consumer = _RecordingConsumer()
        runner = ParallelSweepRunner(
            config=None, n_workers=2, consumer=consumer,
            worker_fn=_stub_run_one_rpm,
            executor_factory=_thread_executor_factory,
        )
        runner.run([8000.0, 10000.0], n_cycles=4)

        types_seen = {type(e).__name__ for e in consumer.events}
        assert "RPMStartEvent" in types_seen
        assert "CycleDoneEvent" in types_seen
        assert "ConvergedEvent" in types_seen
        assert "RPMDoneEvent" in types_seen

    def test_consumer_close_is_called(self):
        consumer = _RecordingConsumer()
        runner = ParallelSweepRunner(
            config=None, n_workers=2, consumer=consumer,
            worker_fn=_stub_run_one_rpm,
            executor_factory=_thread_executor_factory,
        )
        runner.run([8000.0], n_cycles=4)
        assert consumer.closed is True

    def test_rpm_index_matches_submission_order(self):
        consumer = _RecordingConsumer()
        runner = ParallelSweepRunner(
            config=None, n_workers=2, consumer=consumer,
            worker_fn=_stub_run_one_rpm,
            executor_factory=_thread_executor_factory,
        )
        rpm_points = [6000.0, 8000.0, 10000.0, 12000.0]
        runner.run(rpm_points, n_cycles=4)

        starts = [e for e in consumer.events if isinstance(e, RPMStartEvent)]
        # Build rpm -> rpm_index map from the captured events
        idx_by_rpm = {e.rpm: e.rpm_index for e in starts}
        assert idx_by_rpm == {6000.0: 0, 8000.0: 1, 10000.0: 2, 12000.0: 3}

    def test_worker_exception_propagates(self):
        consumer = _RecordingConsumer()
        runner = ParallelSweepRunner(
            config=None, n_workers=2, consumer=consumer,
            worker_fn=_failing_run_one_rpm,
            executor_factory=_thread_executor_factory,
        )
        with pytest.raises(ValueError, match="boom"):
            runner.run([8000.0], n_cycles=4)

    def test_resolve_n_workers_default_uses_cpu_count(self, monkeypatch):
        """The internal _resolve_n_workers helper should clamp the default
        worker count to min(cpu_count, n_rpm_points)."""
        import os
        monkeypatch.setattr(os, "cpu_count", lambda: 4)
        runner = ParallelSweepRunner(
            config=None, n_workers=None, consumer=_RecordingConsumer(),
        )
        # Plenty of RPMs: capped at cpu_count
        assert runner._resolve_n_workers(8) == 4
        # Few RPMs: capped at len(rpm_points)
        assert runner._resolve_n_workers(2) == 2
        # Single RPM: 1 worker
        assert runner._resolve_n_workers(1) == 1

    def test_resolve_n_workers_handles_none_cpu_count(self, monkeypatch):
        """If os.cpu_count() returns None (rare containerized env),
        the resolved worker count must still be at least 1."""
        import os
        monkeypatch.setattr(os, "cpu_count", lambda: None)
        runner = ParallelSweepRunner(
            config=None, n_workers=None, consumer=_RecordingConsumer(),
        )
        assert runner._resolve_n_workers(4) == 1   # min(1, 4) due to `or 1` fallback

    def test_resolve_n_workers_explicit_override(self):
        runner = ParallelSweepRunner(
            config=None, n_workers=3, consumer=_RecordingConsumer(),
        )
        # Explicit n_workers=3, plenty of RPMs: use 3
        assert runner._resolve_n_workers(8) == 3
        # Explicit n_workers=3, only 2 RPMs: clamp to 2 (no idle workers)
        assert runner._resolve_n_workers(2) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd  && .venv/bin/pytest tests/test_parallel_sweep_runner.py -v`
Expected: ImportError because `ParallelSweepRunner` does not exist yet.

---

### Task 10: Implement ParallelSweepRunner

**Files:**
- Modify: `engine_simulator/simulation/parallel_sweep.py`

- [ ] **Step 1: Add the imports needed for the runner**

Find the existing imports at the top of `parallel_sweep.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Union
```

Replace them with:

```python
from __future__ import annotations

import multiprocessing
import os
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from queue import Empty
from typing import Optional, Protocol, Union
```

- [ ] **Step 2: Append ParallelSweepRunner to parallel_sweep.py**

Add this code at the end of `engine_simulator/simulation/parallel_sweep.py`:

```python


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
        queue = ctx.Queue()

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
            try:
                queue.close()
                queue.join_thread()
            except Exception:
                pass
            self.consumer.close()

        return sweep_results, results_by_rpm
```

- [ ] **Step 3: Run the runner tests to verify they pass**

Run: `cd  && .venv/bin/pytest tests/test_parallel_sweep_runner.py -v`
Expected: All 7 tests pass.

- [ ] **Step 4: Run the full test suite to verify nothing regressed**

Run: `cd  && .venv/bin/pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 5: Save progress**

```bash
git add engine_simulator/simulation/parallel_sweep.py tests/test_parallel_sweep_runner.py
git commit -m "feat(parallel): implement ParallelSweepRunner with process pool"
```

---

## Phase G: Wire n_workers Into run_rpm_sweep

Adds the dispatcher inside `run_rpm_sweep` so callers can pass `n_workers` to choose between the sequential and parallel paths.

### Task 11: Add n_workers parameter and dispatch logic

**Files:**
- Modify: `engine_simulator/simulation/orchestrator.py`

- [ ] **Step 1: Add the new params to run_rpm_sweep signature**

Find this signature in `orchestrator.py` (around line 456-463):

```python
    def run_rpm_sweep(
        self,
        rpm_start: Optional[float] = None,
        rpm_end: Optional[float] = None,
        rpm_step: Optional[float] = None,
        n_cycles: int = 5,
        verbose: bool = True,
    ) -> list[dict]:
```

Replace it with:

```python
    def run_rpm_sweep(
        self,
        rpm_start: Optional[float] = None,
        rpm_end: Optional[float] = None,
        rpm_step: Optional[float] = None,
        n_cycles: int = 5,
        verbose: bool = True,
        n_workers: Optional[int] = None,
        consumer: Optional["EventConsumer"] = None,
    ) -> list[dict]:
```

- [ ] **Step 2: Add the parallel-path dispatcher above the sequential loop**

Find the start of the sequential loop in `run_rpm_sweep` (around line 476-486):

```python
        rpm_points = np.arange(rpm_start, rpm_end + rpm_step / 2, rpm_step)
        sweep_results = []

        if verbose:
            print(f"RPM sweep: {rpm_start:.0f} to {rpm_end:.0f} step {rpm_step:.0f}")
            print(f"  {len(rpm_points)} RPM points, {n_cycles} cycles each")

        for rpm in rpm_points:
            self.results = SimulationResults()  # fresh for each RPM
            perf = self.run_single_rpm(rpm, n_cycles=n_cycles, verbose=verbose)
            sweep_results.append(perf)
            # Retain a per-RPM copy so callers (and the future GUI) can
            # access the recorded last-cycle data for every RPM, not just
            # the last one.
            self.results_by_rpm[float(rpm)] = self.results
```

Replace it with:

```python
        rpm_points = np.arange(rpm_start, rpm_end + rpm_step / 2, rpm_step)
        rpm_points_list = [float(r) for r in rpm_points]

        # Decide which code path to take. Compute effective_workers using
        # the same formula ParallelSweepRunner uses, so the print line below
        # accurately reflects what will run.
        if n_workers is None:
            cpu = os.cpu_count() or 1
            effective_workers = max(1, min(cpu, len(rpm_points_list)))
        else:
            effective_workers = max(1, min(n_workers, len(rpm_points_list)))

        if verbose:
            print(f"RPM sweep: {rpm_start:.0f} to {rpm_end:.0f} step {rpm_step:.0f}")
            print(
                f"  {len(rpm_points)} RPM points, {n_cycles} cycles each, "
                f"{effective_workers} worker{'s' if effective_workers != 1 else ''}"
            )

        if effective_workers > 1:
            # Parallel path: delegate to ParallelSweepRunner.
            # Imported lazily so the sequential path doesn't pay the import cost.
            from engine_simulator.simulation.parallel_sweep import (
                CLIEventConsumer,
                ParallelSweepRunner,
            )
            runner = ParallelSweepRunner(
                config=self.config,
                n_workers=effective_workers,
                consumer=consumer or CLIEventConsumer(verbose=verbose),
            )
            sweep_results, results_by_rpm = runner.run(
                rpm_points_list, n_cycles=n_cycles,
            )
            self.results_by_rpm = results_by_rpm
            if results_by_rpm:
                # Backwards compat: self.results points at the last RPM,
                # matching the behavior of the sequential loop.
                self.results = results_by_rpm[rpm_points_list[-1]]
            if verbose:
                self._print_sweep_summary(sweep_results)
            return sweep_results

        # Sequential path: unchanged from before this PR (except results_by_rpm).
        sweep_results = []
        for rpm in rpm_points:
            self.results = SimulationResults()  # fresh for each RPM
            perf = self.run_single_rpm(rpm, n_cycles=n_cycles, verbose=verbose)
            sweep_results.append(perf)
            self.results_by_rpm[float(rpm)] = self.results
```

- [ ] **Step 3: Add the `os` import at the top of orchestrator.py**

Find this block at the top of the file:

```python
"""Main simulation orchestrator: time-stepping loop coupling all subsystems."""

from __future__ import annotations

import time
from typing import Callable, Optional
```

Replace it with:

```python
"""Main simulation orchestrator: time-stepping loop coupling all subsystems."""

from __future__ import annotations

import os
import time
from typing import Callable, Optional
```

- [ ] **Step 4: Verify the orchestrator imports cleanly**

Run: `cd  && .venv/bin/python -c "
from engine_simulator.simulation.orchestrator import SimulationOrchestrator
from engine_simulator.config.engine_config import EngineConfig
sim = SimulationOrchestrator(EngineConfig())
print('ok')
"`
Expected: `ok`

- [ ] **Step 5: Run a sequential sweep with explicit n_workers=1 to verify the sequential path still works**

Run: `cd  && .venv/bin/python -c "
from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator
sim = SimulationOrchestrator(EngineConfig())
sim.run_rpm_sweep(rpm_start=8000, rpm_end=10000, rpm_step=2000, n_cycles=4, verbose=True, n_workers=1)
print('done')
print(sorted(sim.results_by_rpm.keys()))
"`
Expected: Sequential output appears, summary table prints, then `done`, then `[8000.0, 10000.0]`.

- [ ] **Step 6: Run a parallel sweep with n_workers=2 to verify the parallel path works end-to-end**

Run: `cd  && .venv/bin/python -c "
from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator
sim = SimulationOrchestrator(EngineConfig())
sim.run_rpm_sweep(rpm_start=8000, rpm_end=10000, rpm_step=2000, n_cycles=4, verbose=True, n_workers=2)
print('done')
print(sorted(sim.results_by_rpm.keys()))
"`
Expected: Tagged event lines appear (e.g. `[ 8000 RPM] start (rpm_idx 0)`, `[ 8000 RPM] cycle 1 ...`, `[ 8000 RPM] DONE ...`), then the summary table, then `done`, then `[8000.0, 10000.0]`.

- [ ] **Step 7: Run the full test suite**

Run: `cd  && .venv/bin/pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 8: Save progress**

```bash
git add engine_simulator/simulation/orchestrator.py
git commit -m "feat(parallel): wire n_workers dispatcher into run_rpm_sweep"
```

---

## Phase H: CLI Flags

### Task 12: Add --workers and --quiet flags to main.py

**Files:**
- Modify: `engine_simulator/main.py`

- [ ] **Step 1: Add the new arguments to the argparse parser**

Find this block in `engine_simulator/main.py` (around line 122-133):

```python
    parser.add_argument("--rpm", type=float, default=10000.0, help="RPM for single-point run")
    parser.add_argument("--rpm-start", type=float, default=6000.0, help="Sweep start RPM")
    parser.add_argument("--rpm-end", type=float, default=13000.0, help="Sweep end RPM")
    parser.add_argument("--rpm-step", type=float, default=1000.0, help="Sweep RPM step")
    parser.add_argument("--cycles", type=int, default=12, help="Number of engine cycles")
    parser.add_argument("--no-plot", action="store_true", help="Disable plotting")

    args = parser.parse_args()
    do_plot = not args.no_plot
```

Replace it with:

```python
    parser.add_argument("--rpm", type=float, default=10000.0, help="RPM for single-point run")
    parser.add_argument("--rpm-start", type=float, default=6000.0, help="Sweep start RPM")
    parser.add_argument("--rpm-end", type=float, default=13000.0, help="Sweep end RPM")
    parser.add_argument("--rpm-step", type=float, default=1000.0, help="Sweep RPM step")
    parser.add_argument("--cycles", type=int, default=12, help="Number of engine cycles")
    parser.add_argument("--no-plot", action="store_true", help="Disable plotting")
    parser.add_argument(
        "--workers", type=int, default=None,
        help="Number of parallel worker processes for RPM sweep. "
             "Default: min(cpu_count, n_rpm_points). "
             "Use --workers 1 to force the original sequential solver path.",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress per-cycle progress events during the sweep. "
             "The final summary table is still printed.",
    )

    args = parser.parse_args()
    do_plot = not args.no_plot
```

- [ ] **Step 2: Add n_workers and quiet parameters to run_rpm_sweep wrapper in main.py**

Find this function in `engine_simulator/main.py` (around line 90-113):

```python
def run_rpm_sweep(
    rpm_start: float = 6000.0, rpm_end: float = 13000.0, rpm_step: float = 1000.0,
    n_cycles: int = 12, plot: bool = True,
):
    """Run RPM sweep and generate performance curves."""
    from engine_simulator.config.engine_config import EngineConfig
    from engine_simulator.simulation.orchestrator import SimulationOrchestrator

    print(f"\nRunning RPM sweep: {rpm_start:.0f} to {rpm_end:.0f}, step {rpm_step:.0f}")
    config = EngineConfig()
    sim = SimulationOrchestrator(config)
    sweep = sim.run_rpm_sweep(
        rpm_start=rpm_start, rpm_end=rpm_end, rpm_step=rpm_step,
        n_cycles=n_cycles, verbose=True,
    )

    if plot:
        try:
            from engine_simulator.postprocessing.visualization import plot_rpm_sweep
            plot_rpm_sweep(sweep)
        except ImportError:
            print("  (matplotlib not available for plotting)")

    return sweep, sim
```

Replace it with:

```python
def run_rpm_sweep(
    rpm_start: float = 6000.0, rpm_end: float = 13000.0, rpm_step: float = 1000.0,
    n_cycles: int = 12, plot: bool = True,
    n_workers=None, quiet: bool = False,
):
    """Run RPM sweep and generate performance curves."""
    from engine_simulator.config.engine_config import EngineConfig
    from engine_simulator.simulation.orchestrator import SimulationOrchestrator

    print(f"\nRunning RPM sweep: {rpm_start:.0f} to {rpm_end:.0f}, step {rpm_step:.0f}")
    config = EngineConfig()
    sim = SimulationOrchestrator(config)
    sweep = sim.run_rpm_sweep(
        rpm_start=rpm_start, rpm_end=rpm_end, rpm_step=rpm_step,
        n_cycles=n_cycles, verbose=not quiet,
        n_workers=n_workers,
    )

    if plot:
        try:
            from engine_simulator.postprocessing.visualization import plot_rpm_sweep
            plot_rpm_sweep(sweep)
        except ImportError:
            print("  (matplotlib not available for plotting)")

    return sweep, sim
```

- [ ] **Step 3: Thread the new flags through main()**

Find this block in `main()` in `engine_simulator/main.py` (around line 151-156):

```python
    if args.command in ("sweep", "all"):
        sweep, sim = run_rpm_sweep(
            rpm_start=args.rpm_start, rpm_end=args.rpm_end,
            rpm_step=args.rpm_step, n_cycles=args.cycles, plot=do_plot,
        )
```

Replace it with:

```python
    if args.command in ("sweep", "all"):
        sweep, sim = run_rpm_sweep(
            rpm_start=args.rpm_start, rpm_end=args.rpm_end,
            rpm_step=args.rpm_step, n_cycles=args.cycles, plot=do_plot,
            n_workers=args.workers, quiet=args.quiet,
        )
```

- [ ] **Step 4: Verify --help shows the new flags**

Run: `cd  && .venv/bin/python -m engine_simulator.main --help`
Expected: `--workers WORKERS` and `--quiet` appear in the help output.

- [ ] **Step 5: Run a tiny sweep via the CLI in parallel mode**

Run: `cd  && .venv/bin/python -m engine_simulator.main sweep --rpm-start 8000 --rpm-end 10000 --rpm-step 2000 --cycles 4 --workers 2 --no-plot`
Expected: Two RPMs run in parallel, tagged event lines appear, the summary table prints at the end, and the script exits cleanly.

- [ ] **Step 6: Run a tiny sweep via the CLI in --workers 1 mode and verify the old format prints appear**

Run: `cd  && .venv/bin/python -m engine_simulator.main sweep --rpm-start 8000 --rpm-end 10000 --rpm-step 2000 --cycles 4 --workers 1 --no-plot`
Expected: The old inline format prints (`Running 8000 RPM... cycle 1 (delta=0.xxxx) cycle 2 ...`) appear; no tagged event lines appear; the summary table prints at the end.

- [ ] **Step 7: Run the full test suite**

Run: `cd  && .venv/bin/pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 8: Save progress**

```bash
git add engine_simulator/main.py
git commit -m "feat(cli): add --workers and --quiet flags to sweep command"
```

---

## Phase I: Numerical Equivalence Tests (the keystone)

This phase writes the tests that make "the math is unchanged" falsifiable. The Layer 1 test compares perf dicts; the Layer 2 test compares recorded `SimulationResults`.

### Task 13: Write Layer 1 perf-dict equivalence test

**Files:**
- Create: `tests/test_parallel_sweep_equivalence.py`

- [ ] **Step 1: Write the test file**

```python
# tests/test_parallel_sweep_equivalence.py
"""Numerical equivalence between sequential and parallel RPM sweeps.

These are the keystone tests that pin "the math is unchanged" as a hard
falsifiable property. Each worker is a fully-deterministic sequence of
NumPy operations on private state — no shared memory, no parallel
reductions, no atomic ops. Therefore parallel results must be bit-for-bit
identical to sequential results, and the assertion is `==`, not allclose.

If this test ever fails by even one ULP, that's a real plumbing bug
(some shared state leaked, an operation order changed, etc.), not
floating-point noise.
"""

import numpy as np
import pytest

from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator


# Use a small sweep so the test runs in reasonable time. The point is
# correctness, not coverage of every RPM.
RPM_START = 8000
RPM_END = 10000
RPM_STEP = 1000
N_CYCLES = 4


def _run_sequential():
    sim = SimulationOrchestrator(EngineConfig())
    sweep = sim.run_rpm_sweep(
        rpm_start=RPM_START, rpm_end=RPM_END, rpm_step=RPM_STEP,
        n_cycles=N_CYCLES, verbose=False, n_workers=1,
    )
    return sweep, sim


def _run_parallel(n_workers):
    sim = SimulationOrchestrator(EngineConfig())
    sweep = sim.run_rpm_sweep(
        rpm_start=RPM_START, rpm_end=RPM_END, rpm_step=RPM_STEP,
        n_cycles=N_CYCLES, verbose=False, n_workers=n_workers,
    )
    return sweep, sim


class TestPerfDictEquivalence:
    def test_parallel_2_workers_matches_sequential_bit_identical(self):
        seq_results, _seq_sim = _run_sequential()
        par_results, _par_sim = _run_parallel(n_workers=2)

        assert len(seq_results) == len(par_results)
        for seq, par in zip(seq_results, par_results):
            assert seq["rpm"] == par["rpm"]
            for key in seq:
                seq_val = seq[key]
                par_val = par[key]
                if isinstance(seq_val, (int, float)):
                    assert seq_val == par_val, (
                        f"Mismatch at RPM {seq['rpm']} key {key}: "
                        f"seq={seq_val} par={par_val} "
                        f"diff={seq_val - par_val if isinstance(par_val, (int, float)) else 'n/a'}"
                    )
                else:
                    assert seq_val == par_val

    def test_parallel_3_workers_matches_sequential_bit_identical(self):
        # Use a different worker count to verify the result doesn't depend
        # on how many parallel processes are running.
        seq_results, _ = _run_sequential()
        par_results, _ = _run_parallel(n_workers=3)

        assert len(seq_results) == len(par_results)
        for seq, par in zip(seq_results, par_results):
            assert seq["rpm"] == par["rpm"]
            for key in seq:
                seq_val = seq[key]
                par_val = par[key]
                if isinstance(seq_val, (int, float)):
                    assert seq_val == par_val, (
                        f"Mismatch at RPM {seq['rpm']} key {key}: "
                        f"seq={seq_val} par={par_val}"
                    )
                else:
                    assert seq_val == par_val

    def test_rpm_order_preserved_in_parallel_results(self):
        par_results, _ = _run_parallel(n_workers=3)
        rpms = [r["rpm"] for r in par_results]
        assert rpms == sorted(rpms)
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `cd  && .venv/bin/pytest tests/test_parallel_sweep_equivalence.py::TestPerfDictEquivalence -v`
Expected: All 3 tests pass. (This test takes 30-90 seconds because it runs the real solver multiple times.)

- [ ] **Step 3: Save progress**

```bash
git add tests/test_parallel_sweep_equivalence.py
git commit -m "test(parallel): bit-identical perf-dict equivalence test"
```

---

### Task 14: Write Layer 2 SimulationResults equivalence test

**Files:**
- Modify: `tests/test_parallel_sweep_equivalence.py`

- [ ] **Step 1: Append the SimulationResults equivalence test**

Add this code at the end of `tests/test_parallel_sweep_equivalence.py`:

```python


class TestSimulationResultsEquivalence:
    def test_results_by_rpm_arrays_bit_identical(self):
        """Recorded probe data must match between sequential and parallel paths.

        Catches the case where perf dicts match by coincidence but the
        underlying recorded state has drifted (e.g. a serialization
        round-trip dropped a field, an array was rebuilt with different
        dtype, an emit-side mutation got dropped, etc.).
        """
        _seq_perf, seq_sim = _run_sequential()
        _par_perf, par_sim = _run_parallel(n_workers=2)

        assert set(seq_sim.results_by_rpm.keys()) == set(par_sim.results_by_rpm.keys())

        for rpm in sorted(seq_sim.results_by_rpm.keys()):
            seq_r = seq_sim.results_by_rpm[rpm]
            par_r = par_sim.results_by_rpm[rpm]

            # Time history
            assert len(seq_r.theta_history) == len(par_r.theta_history), (
                f"Length mismatch at {rpm} RPM"
            )
            np.testing.assert_array_equal(
                np.asarray(seq_r.theta_history), np.asarray(par_r.theta_history),
                err_msg=f"theta_history at {rpm} RPM",
            )
            np.testing.assert_array_equal(
                np.asarray(seq_r.dt_history), np.asarray(par_r.dt_history),
                err_msg=f"dt_history at {rpm} RPM",
            )

            # Plenum
            np.testing.assert_array_equal(
                np.asarray(seq_r.plenum_pressure), np.asarray(par_r.plenum_pressure),
                err_msg=f"plenum_pressure at {rpm} RPM",
            )
            np.testing.assert_array_equal(
                np.asarray(seq_r.plenum_temperature), np.asarray(par_r.plenum_temperature),
                err_msg=f"plenum_temperature at {rpm} RPM",
            )

            # Restrictor
            np.testing.assert_array_equal(
                np.asarray(seq_r.restrictor_mdot), np.asarray(par_r.restrictor_mdot),
                err_msg=f"restrictor_mdot at {rpm} RPM",
            )

            # Per-cylinder probes
            assert set(seq_r.cylinder_data.keys()) == set(par_r.cylinder_data.keys())
            for cyl_id in seq_r.cylinder_data:
                seq_arrs = seq_r.get_cylinder_arrays(cyl_id)
                par_arrs = par_r.get_cylinder_arrays(cyl_id)
                for k in seq_arrs:
                    np.testing.assert_array_equal(
                        seq_arrs[k], par_arrs[k],
                        err_msg=f"cylinder {cyl_id} {k} at {rpm} RPM",
                    )

            # Per-pipe probes
            assert set(seq_r.pipe_probes.keys()) == set(par_r.pipe_probes.keys())
            for key in seq_r.pipe_probes:
                seq_p = seq_r.pipe_probes[key]
                par_p = par_r.pipe_probes[key]
                np.testing.assert_array_equal(
                    np.asarray(seq_p.pressure), np.asarray(par_p.pressure),
                    err_msg=f"pipe {key} pressure at {rpm} RPM",
                )
                np.testing.assert_array_equal(
                    np.asarray(seq_p.temperature), np.asarray(par_p.temperature),
                    err_msg=f"pipe {key} temperature at {rpm} RPM",
                )
                np.testing.assert_array_equal(
                    np.asarray(seq_p.velocity), np.asarray(par_p.velocity),
                    err_msg=f"pipe {key} velocity at {rpm} RPM",
                )
                np.testing.assert_array_equal(
                    np.asarray(seq_p.density), np.asarray(par_p.density),
                    err_msg=f"pipe {key} density at {rpm} RPM",
                )
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `cd  && .venv/bin/pytest tests/test_parallel_sweep_equivalence.py::TestSimulationResultsEquivalence -v`
Expected: The test passes. (Adds another ~30-90 seconds to the test run.)

- [ ] **Step 3: Run the entire equivalence test file**

Run: `cd  && .venv/bin/pytest tests/test_parallel_sweep_equivalence.py -v`
Expected: All 4 tests pass.

- [ ] **Step 4: Run the full test suite end-to-end**

Run: `cd  && .venv/bin/pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 5: Save progress**

```bash
git add tests/test_parallel_sweep_equivalence.py
git commit -m "test(parallel): SimulationResults bit-identical equivalence test"
```

---

## Phase J: Manual Smoke Test & Speedup Report

Final hand-validation by the user before considering the work complete.

### Task 15: Manual smoke test on the full sweep

**Files:**
- (None — manual verification only)

- [ ] **Step 1: Run the full sweep sequentially and capture output**

Run: `cd  && .venv/bin/python -m engine_simulator.main sweep --rpm-start 6000 --rpm-end 13000 --rpm-step 1000 --cycles 12 --workers 1 --no-plot > /tmp/seq.txt 2>&1`
Expected: Completes successfully, file `/tmp/seq.txt` is populated with the old inline-format output and the summary table.

- [ ] **Step 2: Run the full sweep in parallel and capture output**

Run: `cd  && .venv/bin/python -m engine_simulator.main sweep --rpm-start 6000 --rpm-end 13000 --rpm-step 1000 --cycles 12 --workers 8 --no-plot > /tmp/par.txt 2>&1`
Expected: Completes successfully and noticeably faster than the sequential run. File `/tmp/par.txt` is populated with the tagged event format and the summary table.

- [ ] **Step 3: Compare summary tables — they must be identical**

Run: `diff <(tail -20 /tmp/seq.txt) <(tail -20 /tmp/par.txt)`
Expected: No output (the tail of both files — which contains the summary table — must be byte-identical).

- [ ] **Step 4: Compare wall-clock times and report speedup**

Run: `cd  && time .venv/bin/python -m engine_simulator.main sweep --rpm-start 6000 --rpm-end 13000 --rpm-step 1000 --cycles 12 --workers 1 --no-plot > /dev/null 2>&1`

Then: `cd  && time .venv/bin/python -m engine_simulator.main sweep --rpm-start 6000 --rpm-end 13000 --rpm-step 1000 --cycles 12 --workers 8 --no-plot > /dev/null 2>&1`

Expected: The parallel run takes meaningfully less wall-clock time. On a 10-core machine for an 8-RPM sweep, expect 4-8x speedup. If the speedup is less than ~3x, investigate (likely culprits: tiny per-RPM workload not amortizing spawn cost, or unexpected serialization in the consumer thread).

- [ ] **Step 5: (Optional) Test high-def sweep**

Run: `cd  && time .venv/bin/python -m engine_simulator.main sweep --rpm-start 6000 --rpm-end 13000 --rpm-step 250 --cycles 12 --workers 1 --no-plot > /tmp/hd_seq.txt 2>&1`

Then: `cd  && time .venv/bin/python -m engine_simulator.main sweep --rpm-start 6000 --rpm-end 13000 --rpm-step 250 --cycles 12 --workers 10 --no-plot > /tmp/hd_par.txt 2>&1`

Then: `diff <(tail -40 /tmp/hd_seq.txt) <(tail -40 /tmp/hd_par.txt)`

Expected: No diff output. Speedup should be ≥ 6x (more RPMs amortize spawn cost better).

- [ ] **Step 6: Save progress**

```bash
git add -A
git commit -m "feat(parallel): complete parallel RPM sweep implementation"
```

---

## Spec Coverage Map

For each section of the spec, the corresponding implementation task:

| Spec Section | Implementation Task(s) |
|---|---|
| Architecture: process pool with spawn context | Task 10 (`ParallelSweepRunner.run`) |
| Default `n_workers = min(cpu_count or 1, len(rpm_points))` | Task 10 (`_resolve_n_workers`), Task 11 (orchestrator dispatcher) |
| Event types (RPMStart, CycleDone, Converged, RPMDone, RPMError) | Task 1 (dataclasses) |
| Event emission points in run_single_rpm | Task 5 (Steps 4, 5, 6, 7) |
| `event_callback` parameter, default None preserves old behavior | Task 5 (Step 3) |
| `results_by_rpm` instance attribute | Task 5 (Step 1), Task 6, Task 11 |
| `_last_step_count` and `_last_converged` instance attributes | Task 5 (Steps 1, 7) |
| Sequential path unchanged when `event_callback=None` | Task 5 (every step uses `if event_callback is not None`) |
| `_print_sweep_summary` extraction | Task 7 |
| `_run_one_rpm` worker entry function (top-level, picklable) | Task 8 |
| `ParallelSweepRunner` class | Task 10 |
| RPM order preserved in parallel results | Task 10 (pre-sized list indexed by submission order), Task 13 (`test_rpm_order_preserved_in_parallel_results`) |
| `rpm_index` stable per RPM | Task 8 (re-tagging in worker), Task 9 (`test_rpm_index_matches_submission_order`) |
| `RPMErrorEvent` on worker exception | Task 8 (try/except), Task 9 (`test_worker_exception_propagates`) |
| Daemon pump thread | Task 10 (`_pump_events`) |
| Per-RPM `SimulationResults` returned via future result | Task 8 (return tuple), Task 10 (`results_by_rpm[float(rpm)] = results`) |
| Backwards-compat: `self.results` points at last RPM | Task 11 (Step 2) |
| `n_workers` parameter on `run_rpm_sweep` | Task 11 |
| `--workers` and `--quiet` CLI flags | Task 12 |
| `if __name__ == "__main__": main()` guard already present | (no task — already in place) |
| Layer 1 numerical equivalence test | Task 13 |
| Layer 2 SimulationResults equivalence test | Task 14 |
| Layer 3 plumbing tests (event_consumer, sweep_runner, orchestrator_event_callback) | Task 2, Task 4, Task 9 |
| Layer 4 manual smoke test with diff | Task 15 |
| `--workers 1` falls back to byte-identical sequential output | Task 11 (sequential branch unchanged), Task 12 (Step 6 verifies) |
| Files NOT touched (math files) | Plan does not modify any of: `gas_dynamics/*`, `engine/*`, `boundaries/*`, `simulation/plenum.py`, `convergence.py`, `engine_cycle.py`, `postprocessing/results.py` |

## Decision Recap (from spec, repeated here so the engineer doesn't have to flip)

1. **Process pool, not threads** — Python GIL would defeat NumPy parallelism in threads.
2. **Spawn context, explicit** — uniform behavior across macOS (default spawn) and Linux (default fork).
3. **Default `n_workers = min(cpu_count or 1, len(rpm_points))`** — doesn't oversubscribe for tiny sweeps.
4. **Per-RPM `SimulationResults` preserved on both code paths** — sequential and parallel return the same data shape.
5. **Sequential path is the source of truth, accessible via `--workers 1`** — debugging escape hatch and CI reference.
6. **Structured progress events, not formatted strings** — GUI consumes the same stream as the CLI.
7. **Verbose by default** — user wants maximum information visibility for GUI extraction.
8. **Event prints and event emits are independent** — sequential CLI path is byte-for-byte unchanged in console output.
9. **Inner-loop optimization is out of scope** — `gas_dynamics/moc_solver.py` is the actual single-RPM hot path and is not in this plan.
