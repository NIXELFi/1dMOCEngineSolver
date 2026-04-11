"""Tests for the ParametricEventConsumer bridge."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from engine_simulator.gui.parametric.event_consumer import (
    ParametricEventConsumer,
)
from engine_simulator.simulation.parallel_sweep import (
    ConvergedEvent,
    CycleDoneEvent,
    RPMDoneEvent,
    RPMErrorEvent,
    RPMStartEvent,
)


@pytest.mark.asyncio
async def test_rpm_start_is_rebroadcast_on_parametric_channel():
    broadcast = AsyncMock()
    loop = asyncio.get_running_loop()
    consumer = ParametricEventConsumer(
        loop=loop,
        broadcast_fn=broadcast,
        study_id="param_test",
        parameter_value=0.25,
    )
    consumer.handle(RPMStartEvent(
        rpm=8000.0, rpm_index=2, n_cycles_target=4, ts=1.0,
    ))
    # Give the loop a chance to run the scheduled coroutine
    await asyncio.sleep(0.05)

    broadcast.assert_called_once()
    msg = broadcast.call_args[0][0]
    assert msg["channel"] == "parametric"
    assert msg["type"] == "parametric_rpm_start"
    assert msg["study_id"] == "param_test"
    assert msg["parameter_value"] == 0.25
    assert msg["rpm"] == 8000.0


@pytest.mark.asyncio
async def test_rpm_done_tagged_with_parameter_value():
    broadcast = AsyncMock()
    loop = asyncio.get_running_loop()
    consumer = ParametricEventConsumer(
        loop=loop,
        broadcast_fn=broadcast,
        study_id="param_test",
        parameter_value=0.30,
    )
    consumer.handle(RPMDoneEvent(
        rpm=9000.0,
        perf={"brake_power_hp": 70.0, "brake_torque_Nm": 60.0},
        elapsed=12.5, step_count=4500, converged=True, ts=2.0,
    ))
    await asyncio.sleep(0.05)

    broadcast.assert_called_once()
    msg = broadcast.call_args[0][0]
    assert msg["type"] == "parametric_rpm_done"
    assert msg["parameter_value"] == 0.30
    assert msg["perf"]["brake_power_hp"] == 70.0


@pytest.mark.asyncio
async def test_nonfinite_delta_coerced_to_none():
    broadcast = AsyncMock()
    loop = asyncio.get_running_loop()
    consumer = ParametricEventConsumer(
        loop=loop,
        broadcast_fn=broadcast,
        study_id="param_test",
        parameter_value=0.20,
    )
    consumer.handle(CycleDoneEvent(
        rpm=8000.0, cycle=1, delta=float("inf"),
        p_ivc=(90000.0, 91000.0, 90500.0, 91200.0),
        step_count=100, elapsed=1.5, ts=3.0,
    ))
    await asyncio.sleep(0.05)

    msg = broadcast.call_args[0][0]
    assert msg["delta"] is None


@pytest.mark.asyncio
async def test_converged_event_rebroadcast():
    broadcast = AsyncMock()
    loop = asyncio.get_running_loop()
    consumer = ParametricEventConsumer(
        loop=loop,
        broadcast_fn=broadcast,
        study_id="param_test",
        parameter_value=0.15,
    )
    consumer.handle(ConvergedEvent(rpm=7500.0, cycle=6, ts=4.0))
    await asyncio.sleep(0.05)

    broadcast.assert_called_once()
    msg = broadcast.call_args[0][0]
    assert msg["type"] == "parametric_rpm_converged"
    assert msg["rpm"] == 7500.0
    assert msg["cycle"] == 6
    assert msg["study_id"] == "param_test"
    assert msg["parameter_value"] == 0.15


@pytest.mark.asyncio
async def test_rpm_error_event_rebroadcast():
    broadcast = AsyncMock()
    loop = asyncio.get_running_loop()
    consumer = ParametricEventConsumer(
        loop=loop,
        broadcast_fn=broadcast,
        study_id="param_test",
        parameter_value=0.35,
    )
    consumer.handle(RPMErrorEvent(
        rpm=12000.0,
        error_type="RuntimeError",
        error_msg="divergent",
        traceback="Traceback (most recent call last):\n  ...",
        ts=5.0,
    ))
    await asyncio.sleep(0.05)

    broadcast.assert_called_once()
    msg = broadcast.call_args[0][0]
    assert msg["type"] == "parametric_rpm_error"
    assert msg["rpm"] == 12000.0
    assert msg["error_type"] == "RuntimeError"
    assert msg["error_msg"] == "divergent"
    assert msg["traceback"].startswith("Traceback")
    assert msg["parameter_value"] == 0.35
