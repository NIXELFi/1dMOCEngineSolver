"""ParallelSweepRunner plumbing tests.

These do NOT use the real solver. They inject a stub worker function
and a ThreadPoolExecutor (instead of ProcessPoolExecutor) so the
tests run in-process and don't pay any multiprocessing or pickling cost.
The real-solver equivalence test lives in test_parallel_sweep_equivalence.py.
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
