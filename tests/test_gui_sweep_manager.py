"""SweepManager unit tests.

C2 covers _apply_event in isolation. C3 adds integration tests
for start_sweep / stop_sweep / drain task with stub solvers.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from engine_simulator.simulation.parallel_sweep import (
    ConvergedEvent,
    CycleDoneEvent,
    RPMDoneEvent,
    RPMErrorEvent,
    RPMStartEvent,
)


def _make_state_with_two_rpms():
    """Build a LiveSweepState with two RPM slots in 'queued' state."""
    from engine_simulator.gui.sweep_manager import LiveSweepState
    state = LiveSweepState(
        sweep_id="test",
        status="running",
        config=MagicMock(),
        config_name="test.json",
        rpm_points=[8000.0, 10000.0],
        n_cycles=4,
        n_workers=2,
        started_at="2026-04-08T18:00:00Z",
        rpms={
            8000.0: {"status": "queued", "rpm_index": 0},
            10000.0: {"status": "queued", "rpm_index": 1},
        },
    )
    return state


def _make_manager_for_apply_event_only():
    """Build a SweepManager without starting any threads/tasks.

    For unit-testing _apply_event we just need an instance with a
    ._current attribute.
    """
    from engine_simulator.gui.sweep_manager import SweepManager
    manager = SweepManager.__new__(SweepManager)
    manager._current = _make_state_with_two_rpms()
    return manager


class TestApplyEvent:
    def test_rpm_start_event_marks_running(self):
        manager = _make_manager_for_apply_event_only()
        event = RPMStartEvent(rpm=8000.0, rpm_index=0,
                              n_cycles_target=4, ts=1.0)
        manager._apply_event(event)
        rpm_state = manager._current.rpms[8000.0]
        assert rpm_state["status"] == "running"
        assert rpm_state["current_cycle"] == 0
        assert rpm_state["delta_history"] == []
        assert rpm_state["p_ivc_history"] == []
        assert rpm_state["step_count"] == 0
        assert rpm_state["elapsed"] == 0.0

    def test_cycle_done_event_appends_history(self):
        manager = _make_manager_for_apply_event_only()
        manager._apply_event(RPMStartEvent(
            rpm=8000.0, rpm_index=0, n_cycles_target=4, ts=1.0,
        ))
        manager._apply_event(CycleDoneEvent(
            rpm=8000.0, cycle=1, delta=0.0823,
            p_ivc=(95000.0, 96000.0, 95500.0, 96100.0),
            step_count=1241, elapsed=12.4, ts=2.0,
        ))
        rpm_state = manager._current.rpms[8000.0]
        assert rpm_state["current_cycle"] == 1
        assert rpm_state["delta"] == 0.0823
        assert rpm_state["delta_history"] == [0.0823]
        assert rpm_state["p_ivc_history"] == [
            [95000.0, 96000.0, 95500.0, 96100.0]
        ]
        assert rpm_state["step_count"] == 1241
        assert rpm_state["elapsed"] == 12.4

    def test_converged_event_records_cycle(self):
        manager = _make_manager_for_apply_event_only()
        manager._apply_event(RPMStartEvent(
            rpm=8000.0, rpm_index=0, n_cycles_target=4, ts=1.0,
        ))
        manager._apply_event(ConvergedEvent(rpm=8000.0, cycle=4, ts=5.0))
        rpm_state = manager._current.rpms[8000.0]
        assert rpm_state["converged_at_cycle"] == 4

    def test_rpm_done_event_marks_done_with_perf(self):
        manager = _make_manager_for_apply_event_only()
        manager._apply_event(RPMStartEvent(
            rpm=8000.0, rpm_index=0, n_cycles_target=4, ts=1.0,
        ))
        perf = {
            "rpm": 8000.0, "brake_power_hp": 72.2,
            "brake_torque_Nm": 64.2,
            "volumetric_efficiency_atm": 1.07,
        }
        manager._apply_event(RPMDoneEvent(
            rpm=8000.0, perf=perf, elapsed=11.2, step_count=4523,
            converged=True, ts=12.0,
        ))
        rpm_state = manager._current.rpms[8000.0]
        assert rpm_state["status"] == "done"
        assert rpm_state["perf"] == perf
        assert rpm_state["elapsed"] == 11.2
        assert rpm_state["step_count"] == 4523
        assert rpm_state["converged"] is True

    def test_rpm_error_event_marks_error(self):
        manager = _make_manager_for_apply_event_only()
        manager._apply_event(RPMStartEvent(
            rpm=10000.0, rpm_index=1, n_cycles_target=4, ts=1.0,
        ))
        manager._apply_event(RPMErrorEvent(
            rpm=10000.0, error_type="ValueError",
            error_msg="bad config", traceback="Traceback...\n", ts=2.0,
        ))
        rpm_state = manager._current.rpms[10000.0]
        assert rpm_state["status"] == "error"
        assert rpm_state["error_type"] == "ValueError"
        assert rpm_state["error_msg"] == "bad config"
        assert "Traceback" in rpm_state["traceback"]


class TestSweepLifecycleStub:
    """Lifecycle tests using a stub _run_sweep_blocking that doesn't
    actually call the solver."""

    @pytest.mark.asyncio
    async def test_start_sweep_creates_running_state(self, monkeypatch, tmp_path):
        from engine_simulator.gui.sweep_manager import SweepManager

        async def fake_broadcast(msg): pass
        loop = asyncio.get_running_loop()
        manager = SweepManager(loop, str(tmp_path), fake_broadcast)

        # Stub the runner so we don't actually run the solver
        def stub_blocking(self, params):
            self._current.sweep_results = [
                {"rpm": 8000.0, "brake_power_hp": 72.2,
                 "brake_torque_Nm": 64.2, "volumetric_efficiency_atm": 1.07,
                 "indicated_power_hp": 89.9},
            ]
            self._current.results_by_rpm = {}
        monkeypatch.setattr(SweepManager, "_run_sweep_blocking",
                            stub_blocking)

        # Stub config loading
        monkeypatch.setattr(
            "engine_simulator.gui.sweep_manager.load_config",
            lambda path: MagicMock(),
        )

        # Stub save_sweep so it doesn't try to actually persist
        monkeypatch.setattr(
            "engine_simulator.gui.sweep_manager.save_sweep",
            lambda state, sweeps_dir: "stub.json",
        )

        params = {
            "rpm_start": 8000, "rpm_end": 8000, "rpm_step": 1000,
            "n_cycles": 4, "n_workers": 1, "config_name": "cbr600rr.json",
        }
        sweep_id = await manager.start_sweep(params)

        assert sweep_id is not None
        assert manager.current is not None
        assert manager.current.config_name == "cbr600rr.json"
        assert 8000.0 in manager.current.rpms

        # Wait for the background sweep task to finish
        await asyncio.wait_for(manager._sweep_task, timeout=2.0)
        await asyncio.wait_for(manager._drain_task, timeout=2.0)

        assert manager.current.status == "complete"

    @pytest.mark.asyncio
    async def test_start_sweep_raises_if_already_running(
        self, monkeypatch, tmp_path,
    ):
        from engine_simulator.gui.sweep_manager import SweepManager, LiveSweepState

        async def fake_broadcast(msg): pass
        loop = asyncio.get_running_loop()
        manager = SweepManager(loop, str(tmp_path), fake_broadcast)

        # Hand-craft a running state
        manager._current = LiveSweepState(
            sweep_id="test", status="running",
            config=MagicMock(), config_name="test.json",
            rpm_points=[8000.0], n_cycles=4, n_workers=1,
            started_at="2026-04-08T18:00:00Z",
            rpms={8000.0: {"status": "running"}},
        )

        params = {
            "rpm_start": 8000, "rpm_end": 8000, "rpm_step": 1000,
            "n_cycles": 4, "n_workers": 1, "config_name": "cbr600rr.json",
        }
        with pytest.raises(RuntimeError, match="already running"):
            await manager.start_sweep(params)

    @pytest.mark.asyncio
    async def test_drain_task_processes_events_in_order(
        self, monkeypatch, tmp_path,
    ):
        from engine_simulator.gui.sweep_manager import SweepManager, LiveSweepState
        from engine_simulator.gui.gui_event_consumer import GUIEventConsumer

        broadcast_log = []
        async def fake_broadcast(msg):
            broadcast_log.append(msg)

        loop = asyncio.get_running_loop()
        manager = SweepManager(loop, str(tmp_path), fake_broadcast)

        manager._current = LiveSweepState(
            sweep_id="test", status="running",
            config=MagicMock(), config_name="test.json",
            rpm_points=[8000.0], n_cycles=4, n_workers=1,
            started_at="2026-04-08T18:00:00Z",
            rpms={8000.0: {"status": "queued", "rpm_index": 0}},
        )
        manager._consumer = GUIEventConsumer(loop)

        # Start the drain task
        manager._drain_task = asyncio.create_task(manager._drain_events())

        # Push some events
        manager._consumer.handle(RPMStartEvent(
            rpm=8000.0, rpm_index=0, n_cycles_target=4, ts=1.0,
        ))
        manager._consumer.handle(CycleDoneEvent(
            rpm=8000.0, cycle=1, delta=0.05,
            p_ivc=(95000.0, 96000.0, 95500.0, 96100.0),
            step_count=100, elapsed=0.1, ts=2.0,
        ))
        manager._consumer.handle(RPMDoneEvent(
            rpm=8000.0,
            perf={"rpm": 8000.0, "brake_power_hp": 72.2,
                  "brake_torque_Nm": 64.2,
                  "volumetric_efficiency_atm": 1.07},
            elapsed=11.2, step_count=4523, converged=True, ts=12.0,
        ))
        manager._consumer.close()

        # Wait for drain task to process the sentinel
        await asyncio.wait_for(manager._drain_task, timeout=2.0)

        # State should be updated
        assert manager.current.rpms[8000.0]["status"] == "done"
        assert manager.current.rpms[8000.0]["perf"]["brake_power_hp"] == 72.2

        # All events should have been broadcast
        broadcast_types = [m.get("type") for m in broadcast_log]
        assert "rpm_start" in broadcast_types
        assert "cycle_done" in broadcast_types
        assert "rpm_done" in broadcast_types
