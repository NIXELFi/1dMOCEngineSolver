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
