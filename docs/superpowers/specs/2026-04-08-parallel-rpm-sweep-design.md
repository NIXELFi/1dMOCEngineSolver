# Parallel RPM Sweep — Design

**Date:** 2026-04-08
**Author:** brainstormed with Claude
**Status:** Approved (pending implementation pause for drivetrain-losses work to land first)

## Motivation

The 1D engine simulator currently runs RPM sweeps sequentially in `SimulationOrchestrator.run_rpm_sweep` (`engine_simulator/simulation/orchestrator.py:483`). Each RPM point is fully independent — `_reinitialize(rpm)` resets all pipe, cylinder, plenum, and restrictor state at the top of `run_single_rpm`, and the orchestrator's only inter-RPM coupling is reusing the constructed pipe/cylinder/boundary objects (which are immediately re-initialized anyway). On a 10-core machine, an 8-RPM sweep is leaving roughly 7 cores idle and a 30-RPM high-def sweep is leaving roughly 9 cores idle.

This design parallelizes the sweep across RPM points using a process pool, with **zero changes to the underlying math** and a structured progress-event stream that a future GUI can consume directly.

## Hard Constraints

1. **No mathematical changes.** The exact same `advance_interior_points`, `extrapolate_boundary_incoming`, `cylinder.advance`, `restrictor_plenum.solve_and_apply`, and so on must run inside each worker, in the same order, with the same arguments, on the same initial state. Bit-for-bit identical perf-dict outputs vs. the sequential path are the acceptance criterion.
2. **Sequential path preserved.** The original `for rpm in rpm_points` loop remains accessible via `--workers 1` (or by calling `run_rpm_sweep(n_workers=1)` programmatically) and produces byte-identical console output to today.
3. **GUI-ready progress reporting.** A future GUI is in scope for the project. The progress mechanism we build now must be the same one the GUI consumes later — no second refactor.
4. **Maximum information visibility.** Per-cycle progress from every running worker must be visible live, not buffered until the end of the sweep.

## Out of Scope (deliberately)

- Speeding up a single RPM point (the inner `for i in range(1, n-1)` loop in `gas_dynamics/moc_solver.py:126`). That is the actual hot path inside one RPM and would require Numba/Cython/vectorization; doing so could perturb floating-point rounding and would need its own equivalence study. Separate spec.
- The GUI itself. This spec only commits to a progress-event API the GUI will consume; it does not implement any GUI.
- Distributed (multi-machine) parallelism.
- Sharing solver state across RPMs (warm-starting cycle 1 of RPM N+1 from cycle ∞ of RPM N). Each RPM still calls `_reinitialize` exactly as today.

## Architecture

**Process-pool parallelism at the RPM level**, using `concurrent.futures.ProcessPoolExecutor` with `mp_context = multiprocessing.get_context("spawn")` for cross-platform consistency.

**Why processes:** Python's GIL would serialize NumPy-array Python loops in threads. Processes give true parallelism. Per-RPM workload is large enough that the spawn cost (~100-200 ms) is negligible against minutes of solver work.

**Why a process pool, not one process per RPM:** high-def sweeps have more RPM points than cores. The pool reuses workers across multiple RPMs to amortize spawn cost.

**Default worker count:** `min(os.cpu_count() or 1, len(rpm_points))`. The `or 1` guards against `os.cpu_count()` returning `None` in rare containerized environments. Override via `--workers N`. `--workers 1` falls back to the sequential path.

### Data flow

```
                                       ┌─────────────────────────┐
                                       │   Parent process        │
                                       │                         │
   ┌──────────────────────────┐        │   ParallelSweepRunner   │
   │  EngineConfig (pickled)  │───────►│                         │
   └──────────────────────────┘        │   ┌─────────────────┐   │
                                       │   │ pump_thread     │   │
   ┌──────────────────────────┐        │   │ (drains queue)  │   │
   │  multiprocessing.Queue   │◄───────┤   └────────┬────────┘   │
   │  (small events only)     │        │            │            │
   └──────────────────────────┘        │            ▼            │
            ▲ ▲ ▲                      │   ┌─────────────────┐   │
            │ │ │                      │   │ EventConsumer   │   │
            │ │ │                      │   │ (CLI today,     │   │
            │ │ │                      │   │  GUI tomorrow)  │   │
            │ │ │                      │   └─────────────────┘   │
            │ │ │                      │                         │
            │ │ │                      │   ProcessPoolExecutor   │
            │ │ │                      │   ┌─────┐ ┌─────┐ ┌───┐ │
            │ │ └──────────────────────┼───┤ W0  │ │ W1  │ │.. │ │
            │ └────────────────────────┼───┤     │ │     │ │   │ │
            └──────────────────────────┼───┤     │ │     │ │   │ │
                                       │   └──┬──┘ └──┬──┘ └─┬─┘ │
                                       │      │       │      │   │
                                       │      ▼       ▼      ▼   │
                                       │   future.result() = (rpm,│
                                       │   perf_dict, SimResults) │
                                       └─────────────────────────┘
```

The queue carries **small, frequent** events (RPMStart, CycleDone, Converged, RPMDone, RPMError) — picklable dataclasses, kilobytes at most. The **large** per-RPM payload (the recorded `SimulationResults` for that RPM's last cycle) flows back through `future.result()`, which is what `ProcessPoolExecutor` does best (pickle-over-pipe).

## File Layout

### New file

**`engine_simulator/simulation/parallel_sweep.py`** — contains everything new:

- Event dataclasses: `RPMStartEvent`, `CycleDoneEvent`, `ConvergedEvent`, `RPMDoneEvent`, `RPMErrorEvent`
- A `ProgressEvent` type alias (union of all event types)
- `EventConsumer` protocol with `handle(event)` and `close()` methods
- `CLIEventConsumer(verbose=True)` — default consumer; prints tagged lines to stdout
- `_run_one_rpm(config, rpm, n_cycles, queue, rpm_index)` — top-level worker entry function (must be top-level so it pickles for spawn)
- `ParallelSweepRunner(config, n_workers, consumer)` — public API; `.run(rpm_points, n_cycles)` returns `(sweep_results: list[dict], results_by_rpm: dict[float, SimulationResults])`

### Modified files

**`engine_simulator/simulation/orchestrator.py`**:

1. New instance attributes in `__init__`:
   - `self.results_by_rpm: dict[float, SimulationResults] = {}`
   - `self._last_step_count: int = 0`
   - `self._last_converged: bool = False`
2. `run_single_rpm` gains an optional `event_callback: Callable[[ProgressEvent], None] | None = None` parameter. When `None` (the default), the existing print-based output runs unchanged. When provided, the orchestrator additionally emits events at the same code points where prints happen. At the end of the function, it sets `self._last_step_count` and `self._last_converged` before returning.
3. `run_rpm_sweep` gains optional `n_workers: int | None = None` and `consumer: EventConsumer | None = None` parameters. When `n_workers != 1`, it delegates to `ParallelSweepRunner` and stores the returned `results_by_rpm` on `self.results_by_rpm`. The sequential path is unchanged except for one new line per RPM that copies `self.results` into `self.results_by_rpm`.
4. The summary-table-printing block at the bottom of `run_rpm_sweep` is extracted into a private helper `self._print_sweep_summary(sweep_results)`. Pure code move, zero formatting change. Both code paths call it.

**`engine_simulator/main.py`**:

- New CLI flags `--workers <int>` and `--quiet`
- These thread through `run_rpm_sweep(...)` to `sim.run_rpm_sweep(...)`

### Files NOT modified

- `engine_simulator/gas_dynamics/moc_solver.py` — all of the math
- `engine_simulator/gas_dynamics/pipe.py`, `cfl.py`, `gas_properties.py`
- `engine_simulator/engine/cylinder.py`, `valve.py`, `kinematics.py`
- `engine_simulator/boundaries/*`
- `engine_simulator/simulation/plenum.py`, `convergence.py`, `engine_cycle.py`
- `engine_simulator/postprocessing/results.py` (`SimulationResults` is already picklable as-is)
- `_run_sweep.py`, `_run_sweep_fast.py` (custom drivers; they call `run_single_rpm` directly and are unaffected)

## Event Model

All event types are frozen dataclasses, picklable, GUI-friendly, and carry `rpm` so the consumer can route them per-panel.

```python
@dataclass(frozen=True)
class RPMStartEvent:
    rpm: float
    rpm_index: int        # the RPM's position in rpm_points (0..len-1).
                          # Stable per RPM. The GUI can use this as a
                          # lane identifier OR maintain its own lane pool
                          # by tracking start/done events.
    n_cycles_target: int
    ts: float             # time.monotonic() in the worker

@dataclass(frozen=True)
class CycleDoneEvent:
    rpm: float
    cycle: int            # 1-indexed cycle that just finished
    delta: float          # convergence.max_relative_change()
    p_ivc: tuple[float, ...]   # per-cylinder p_at_IVC
    step_count: int       # cumulative steps so far this RPM
    elapsed: float        # wall-clock seconds since RPMStartEvent
    ts: float

@dataclass(frozen=True)
class ConvergedEvent:
    rpm: float
    cycle: int            # cycle at which convergence was detected
    ts: float

@dataclass(frozen=True)
class RPMDoneEvent:
    rpm: float
    perf: dict            # the same dict run_single_rpm returns today
    elapsed: float
    step_count: int
    converged: bool       # did convergence fire, or hit n_cycles cap
    ts: float

@dataclass(frozen=True)
class RPMErrorEvent:
    rpm: float
    error_type: str       # exception class name
    error_msg: str
    traceback: str        # formatted traceback
    ts: float
```

### Where events are emitted in `run_single_rpm`

| Event | Code point | Existing print there |
|---|---|---|
| `RPMStartEvent` | Top of function, after `_reinitialize` | `print(f"  Running {rpm:.0f} RPM...", end="")` |
| `CycleDoneEvent` | Inside cycle-boundary block, after `convergence.record_cycle` | `print(f" cycle {new_cycle} (delta={change:.4f})", end="")` |
| `ConvergedEvent` | Where `if convergence.is_converged() and new_cycle >= 3:` fires | `print(" [converged]", end="")` |
| `RPMDoneEvent` | After loop, after `_compute_performance(rpm)` | `print(f" ({elapsed:.1f}s, {step_count} steps)")` |
| `RPMErrorEvent` | Wrapped around the worker entry; only emitted by `_run_one_rpm`, never by the orchestrator itself | (no equivalent today — exceptions kill the sweep) |

**Backwards-compat rule:** prints and emits are independent. When `event_callback is None and verbose=True` (sequential CLI default), only the prints fire. When `verbose=False and event_callback is not None` (worker default), only the events fire. The two paths never interfere.

### CLI consumer output format

```
[ 6000 RPM] start (rpm_idx 0)
[ 8000 RPM] start (rpm_idx 1)
[10000 RPM] start (rpm_idx 2)
[ 6000 RPM] cycle 1  delta=0.0823  steps=1241
[10000 RPM] cycle 1  delta=0.0712  steps=1198
[ 8000 RPM] cycle 1  delta=0.0945  steps=1167
[ 6000 RPM] cycle 2  delta=0.0341  steps=2487
[ 8000 RPM] [converged] at cycle 4
[ 8000 RPM] DONE  P_brk=68.2 hp  T_brk=51.3 Nm  VE_atm=92.4%  (11.2s, 4523 steps)
[ 6000 RPM] cycle 3  delta=0.0118  steps=3719
...
```

After all RPMs finish, `CLIEventConsumer.close()` triggers the existing summary table from `_print_sweep_summary(...)`, so the post-sweep output is byte-identical to today.

## Worker Lifecycle

```python
def _run_one_rpm(
    config: EngineConfig,
    rpm: float,
    n_cycles: int,
    queue: multiprocessing.Queue,
    rpm_index: int,
) -> tuple[float, dict, SimulationResults]:
    """Worker entry: build a fresh orchestrator, run one RPM, return results."""
    import time, traceback
    from engine_simulator.simulation.orchestrator import SimulationOrchestrator

    t_start = time.monotonic()
    try:
        sim = SimulationOrchestrator(config)

        def emit(event):
            queue.put(event)

        emit(RPMStartEvent(
            rpm=rpm, rpm_index=rpm_index,
            n_cycles_target=n_cycles, ts=time.monotonic(),
        ))

        perf = sim.run_single_rpm(
            rpm,
            n_cycles=n_cycles,
            verbose=False,          # suppress orchestrator's print path
            event_callback=emit,
        )

        elapsed = time.monotonic() - t_start
        emit(RPMDoneEvent(
            rpm=rpm, perf=perf, elapsed=elapsed,
            step_count=sim._last_step_count,
            converged=sim._last_converged,
            ts=time.monotonic(),
        ))

        return (rpm, perf, sim.results)

    except Exception as exc:
        queue.put(RPMErrorEvent(
            rpm=rpm,
            error_type=type(exc).__name__,
            error_msg=str(exc),
            traceback=traceback.format_exc(),
            ts=time.monotonic(),
        ))
        raise
```

### `ParallelSweepRunner.run()`

```python
def run(self, rpm_points, n_cycles):
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()

    pump_done = threading.Event()
    pump_thread = threading.Thread(
        target=self._pump_events,
        args=(queue, pump_done),
        daemon=True,
    )
    pump_thread.start()

    sweep_results: list[dict] = [None] * len(rpm_points)   # pre-sized for order
    results_by_rpm: dict[float, SimulationResults] = {}

    with ProcessPoolExecutor(max_workers=self.n_workers, mp_context=ctx) as pool:
        futures = {
            pool.submit(
                _run_one_rpm, self.config, rpm, n_cycles, queue, idx,
            ): idx
            for idx, rpm in enumerate(rpm_points)
        }

        for future in as_completed(futures):
            idx = futures[future]
            rpm, perf, results = future.result()   # raises on worker exception
            sweep_results[idx] = perf
            results_by_rpm[rpm] = results

    pump_done.set()
    pump_thread.join(timeout=2.0)
    queue.close()
    queue.join_thread()
    self.consumer.close()

    return sweep_results, results_by_rpm
```

### Key properties

1. **RPM order is preserved.** `sweep_results` is a pre-sized list indexed by submission order. The returned list is in RPM order regardless of which workers finish first.
2. **`rpm_index` is stable per RPM.** All events from one RPM carry the same `rpm_index` (its position in `rpm_points`), so the GUI can use it as a stable identifier when rendering per-RPM panels. The GUI is also free to ignore it and assign its own lanes by tracking start/done event pairs.
3. **Errors propagate.** A worker exception is captured into an `RPMErrorEvent` for live display, then re-raised inside `future.result()` so the sweep aborts loudly.
4. **Spawn context is explicit and cross-platform.** Forces spawn on Linux (which defaults to fork), avoiding fork-after-multithreading footguns.
5. **Daemon pump thread.** Uses `queue.get(timeout=0.1)` in a loop guarded by `pump_done`. Worst case at shutdown: ~100 ms idle polling. No risk of hanging if a worker dies.
6. **Per-RPM SimulationResults via future.result(), not the queue.** Keeps the queue small and the pump thread fast.

## CLI Changes

```python
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
```

### Compatibility

| Invocation | Before | After |
|---|---|---|
| `main.py validate` | runs validation | unchanged |
| `main.py single --rpm 10000` | runs one RPM | unchanged |
| `main.py sweep` | sequential, verbose | parallel, verbose, **same numerical results** |
| `main.py all` | validate + sweep + published comparison | same, sweep portion is parallel |
| `main.py sweep --no-plot` | sweep without plots | unchanged + parallel |
| `main.py sweep --workers 1` | (didn't exist) | sequential path, byte-identical output to today |

The `if __name__ == "__main__": main()` guard at the bottom of `main.py` is already present (required for spawn-mode workers).

## Testing

### Layer 1 — Numerical equivalence (most important)

`tests/test_parallel_sweep_equivalence.py::test_parallel_sweep_matches_sequential` runs a small sweep (4 RPM points × 6 cycles) both ways and asserts every perf-dict field matches with `==` (not `np.isclose`). Bit-identical is the right standard because each worker is a fully deterministic sequence of NumPy operations on private state — no shared memory, no parallel reductions, no atomic ops. If this test fails by even one ULP, that's a real plumbing bug, not numerical noise.

### Layer 2 — `SimulationResults` equivalence

`tests/test_parallel_sweep_equivalence.py::test_parallel_sweep_results_by_rpm_match_sequential` compares `sim.results_by_rpm` between paths using `np.testing.assert_array_equal` on theta_history, dt_history, plenum_pressure, restrictor_mdot, per-cylinder probe arrays, and per-pipe probe arrays. Catches the case where perf dicts match but the recorded state has drifted.

### Layer 3 — Plumbing tests (independent of solver math)

- `tests/test_event_consumer.py`: pass synthetic events into `CLIEventConsumer`, assert formatted output matches inline expected strings. Catches accidental format changes.
- `tests/test_parallel_sweep_runner.py`: run `ParallelSweepRunner.run()` with a stub worker function returning canned perf dicts. Asserts result list is in RPM order, `results_by_rpm` is keyed correctly, all event types appear in the consumer log, `rpm_index` values match submission order, and worker exceptions propagate as both an `RPMErrorEvent` and a raised exception out of `runner.run()`.
- `tests/test_orchestrator_event_callback.py`: run `run_single_rpm` with a recording event_callback. Assert the events emitted match the print statements one-for-one.

### Layer 4 — Manual smoke test (one-time, before merging)

```bash
python -m engine_simulator.main sweep --rpm-start 6000 --rpm-end 13000 --rpm-step 1000 --workers 1 --no-plot > /tmp/seq.txt
python -m engine_simulator.main sweep --rpm-start 6000 --rpm-end 13000 --rpm-step 1000 --workers 8 --no-plot > /tmp/par.txt
diff <(tail -20 /tmp/seq.txt) <(tail -20 /tmp/par.txt)
# Expected: nothing.
```

### Anti-tests (deliberately not tested)

- **Wall-clock speedup.** Flaky on shared CI; user validates manually. Target: 6-8× on a 10-core machine for an 8-RPM sweep; 8-10× for a 30-RPM sweep with `n_workers=10`.
- **Worker count auto-detection.** Mocking `os.cpu_count()` is brittle and the path is exercised via the equivalence test anyway.

## Decision Log

1. **Process pool, not threads** — GIL would defeat the purpose for NumPy Python loops.
2. **Spawn context, explicit** — uniform behavior across macOS (default spawn) and Linux (default fork). Avoids fork-after-multithreading bugs.
3. **Process pool, not one-process-per-RPM** — high-def sweeps may have more RPMs than cores.
4. **Default `n_workers = min(cpu_count, len(rpm_points))`** — uses available cores without oversubscribing for tiny sweeps.
5. **Per-RPM SimulationResults preserved on both code paths** — sequential and parallel return the same data shape, GUI doesn't have to branch on which path produced the data.
6. **Sequential path is the source of truth, kept accessible via `--workers 1`** — provides a debugging escape hatch and a CI reference for the equivalence test.
7. **Structured progress events, not formatted strings** — the GUI consumes the same stream the CLI does, so no double refactor when the GUI lands.
8. **Verbose by default** — user wants maximum information visibility for GUI extraction. `--quiet` opts out.
9. **Event prints and event emits are independent** — sequential CLI path is byte-for-byte unchanged in console output (uses prints, no events). Worker path uses events, no prints. The two never interfere.
10. **Inner-loop optimization is out of scope** — `gas_dynamics/moc_solver.py` would need a separate equivalence study and is the actual hot path inside one RPM. Not this spec.

## Implementation Sequencing

When implementation begins (after the drivetrain-losses work currently in flight on a separate CLI lands), the order is:

1. Add `event_callback` plumbing to `run_single_rpm` (no behavior change yet, all callers still pass `None`)
2. Add `results_by_rpm` collection to the sequential `run_rpm_sweep` (no behavior change yet)
3. Extract `_print_sweep_summary` (pure code move)
4. Run existing tests; sequential output should be byte-identical
5. Create `parallel_sweep.py` with event dataclasses and `CLIEventConsumer`
6. Add `_run_one_rpm` worker function and `ParallelSweepRunner`
7. Wire `n_workers` parameter into `run_rpm_sweep`
8. Add `--workers` and `--quiet` CLI flags
9. Write Layer 1 + 2 equivalence tests; iterate until they pass with `==`
10. Write Layer 3 plumbing tests
11. Manual smoke test (Layer 4) and report speedup

Each numbered step is small and independently verifiable. Steps 1-4 leave the codebase functionally unchanged but prepared for parallelism; an early run of the existing test suite at step 4 should be a no-op.
