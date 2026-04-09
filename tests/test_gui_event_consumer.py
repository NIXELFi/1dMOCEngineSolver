"""GUIEventConsumer tests.

Verifies the consumer correctly drains events into an asyncio queue
when called from a non-asyncio thread (which is how it's invoked
inside the parallel sweep runner's pump thread).
"""

import asyncio
import threading
import time

import pytest

from engine_simulator.simulation.parallel_sweep import (
    CycleDoneEvent,
    RPMStartEvent,
    RPMDoneEvent,
)


class TestGUIEventConsumer:
    @pytest.mark.asyncio
    async def test_handle_from_main_thread_puts_on_queue(self):
        from engine_simulator.gui.gui_event_consumer import GUIEventConsumer

        loop = asyncio.get_running_loop()
        consumer = GUIEventConsumer(loop)

        event = RPMStartEvent(
            rpm=8000.0, rpm_index=0, n_cycles_target=4, ts=1.0,
        )
        consumer.handle(event)

        # Give the loop a tick to process the call_soon_threadsafe
        await asyncio.sleep(0.01)
        result = await asyncio.wait_for(consumer.queue.get(), timeout=1.0)
        assert result is event

    @pytest.mark.asyncio
    async def test_handle_from_worker_thread_puts_on_queue(self):
        """The critical case: handle() called from a non-asyncio thread."""
        from engine_simulator.gui.gui_event_consumer import GUIEventConsumer

        loop = asyncio.get_running_loop()
        consumer = GUIEventConsumer(loop)

        events_to_send = [
            RPMStartEvent(rpm=8000.0, rpm_index=0, n_cycles_target=4, ts=1.0),
            CycleDoneEvent(rpm=8000.0, cycle=1, delta=0.05,
                           p_ivc=(95000.0, 96000.0, 95500.0, 96100.0),
                           step_count=100, elapsed=0.1, ts=1.5),
            RPMDoneEvent(rpm=8000.0,
                         perf={"brake_power_hp": 72.2,
                               "brake_torque_Nm": 64.2,
                               "volumetric_efficiency_atm": 1.07},
                         elapsed=11.2, step_count=4523,
                         converged=True, ts=12.0),
        ]

        def push_from_thread():
            for ev in events_to_send:
                consumer.handle(ev)

        thread = threading.Thread(target=push_from_thread, daemon=True)
        thread.start()
        thread.join(timeout=1.0)

        # Drain the queue
        received = []
        for _ in range(len(events_to_send)):
            ev = await asyncio.wait_for(consumer.queue.get(), timeout=1.0)
            received.append(ev)

        assert received == events_to_send

    @pytest.mark.asyncio
    async def test_close_puts_sentinel(self):
        from engine_simulator.gui.gui_event_consumer import GUIEventConsumer

        loop = asyncio.get_running_loop()
        consumer = GUIEventConsumer(loop)

        consumer.close()

        await asyncio.sleep(0.01)
        result = await asyncio.wait_for(consumer.queue.get(), timeout=1.0)
        assert result is None  # sentinel

    @pytest.mark.asyncio
    async def test_handle_after_loop_closed_does_not_raise(self):
        """If the asyncio loop has been closed (sweep shutting down),
        handle() must silently drop the event instead of raising."""
        from engine_simulator.gui.gui_event_consumer import GUIEventConsumer

        loop = asyncio.get_running_loop()
        consumer = GUIEventConsumer(loop)

        # Simulate a closed loop by patching the consumer's loop reference
        # to one that's been stopped
        import asyncio as _aio
        dead_loop = _aio.new_event_loop()
        dead_loop.close()
        consumer._loop = dead_loop

        event = RPMStartEvent(rpm=8000.0, rpm_index=0, n_cycles_target=4, ts=1.0)
        # Must not raise
        consumer.handle(event)
