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
