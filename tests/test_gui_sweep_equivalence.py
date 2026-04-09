"""Numerical equivalence between GUI and CLI sweep paths.

The keystone test that pins "the math is unchanged" as a hard
falsifiable property for the GUI integration. The GUI's SweepManager
calls into SimulationOrchestrator.run_rpm_sweep with the same arguments
the CLI does — only the consumer differs (GUIEventConsumer vs
CLIEventConsumer). Both consumers are pure observers and don't mutate
solver state, so the numerical output must be bit-for-bit identical.
"""

import asyncio
from pathlib import Path

import pytest

from engine_simulator.gui.sweep_manager import (
    _resolve_config_path,
    load_config,
)
from engine_simulator.simulation.orchestrator import SimulationOrchestrator


# Use a small sweep so the test runs in reasonable time.
RPM_START = 8000
RPM_END = 10000
RPM_STEP = 1000
N_CYCLES = 4
N_WORKERS = 2
CONFIG_NAME = "cbr600rr.json"


def _run_cli_sweep():
    # Load the SAME config the GUI path loads, so this is a true
    # apples-to-apples comparison of the sweep paths (not the configs).
    config = load_config(_resolve_config_path(CONFIG_NAME))
    sim = SimulationOrchestrator(config)
    sweep = sim.run_rpm_sweep(
        rpm_start=RPM_START, rpm_end=RPM_END, rpm_step=RPM_STEP,
        n_cycles=N_CYCLES, verbose=False, n_workers=N_WORKERS,
    )
    return sweep


async def _run_gui_sweep(tmp_path, monkeypatch):
    """Drive SweepManager directly with a fake broadcast fn.

    Stubs save_sweep so the test doesn't need persistence.py to exist
    (Phase E hasn't been implemented yet at the time this test runs)."""
    from engine_simulator.gui.sweep_manager import SweepManager

    # Stub save_sweep so we don't depend on persistence.py
    monkeypatch.setattr(
        "engine_simulator.gui.sweep_manager.save_sweep",
        lambda state, sweeps_dir: "stub.json",
    )

    received_messages = []
    async def fake_broadcast(msg):
        received_messages.append(msg)

    loop = asyncio.get_running_loop()
    manager = SweepManager(loop, str(tmp_path), fake_broadcast)

    params = {
        "rpm_start": RPM_START,
        "rpm_end": RPM_END,
        "rpm_step": RPM_STEP,
        "n_cycles": N_CYCLES,
        "n_workers": N_WORKERS,
        "config_name": CONFIG_NAME,
    }
    await manager.start_sweep(params)

    # Wait for the sweep to complete (the real solver will take a few minutes)
    await asyncio.wait_for(manager._sweep_task, timeout=900)

    return manager.current.sweep_results, received_messages


class TestGuiSweepEquivalence:
    @pytest.mark.asyncio
    async def test_gui_sweep_matches_cli_bit_identical(
        self, tmp_path, monkeypatch,
    ):
        cli_results = _run_cli_sweep()
        gui_results, _msgs = await _run_gui_sweep(tmp_path, monkeypatch)

        assert len(cli_results) == len(gui_results)
        for cli, gui in zip(cli_results, gui_results):
            assert cli["rpm"] == gui["rpm"]
            for key in cli:
                cli_val, gui_val = cli[key], gui[key]
                if isinstance(cli_val, (int, float)):
                    assert cli_val == gui_val, (
                        f"Mismatch at RPM {cli['rpm']} key {key}: "
                        f"cli={cli_val} gui={gui_val}"
                    )
                else:
                    assert cli_val == gui_val
