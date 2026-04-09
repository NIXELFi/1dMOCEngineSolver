"""GUIEventConsumer - bridges the parallel sweep runner's event stream
to an asyncio queue that the WebSocket pump drains.

Implements the EventConsumer protocol from
engine_simulator.simulation.parallel_sweep. The runner's pump thread calls
handle() on this consumer for every event; we use call_soon_threadsafe
to safely push events onto the asyncio queue from the non-asyncio thread.
"""

from __future__ import annotations

import asyncio

from engine_simulator.simulation.parallel_sweep import ProgressEvent


class GUIEventConsumer:
    """Drains progress events into an asyncio queue.

    Owned by the SweepManager for the duration of one sweep.
    handle() is called from a non-asyncio thread (the parallel sweep
    runner's pump thread); we marshal back to the main asyncio loop
    via call_soon_threadsafe.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._queue: asyncio.Queue = asyncio.Queue()

    def handle(self, event: ProgressEvent) -> None:
        """Push an event onto the asyncio queue (cross-thread safe)."""
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        except RuntimeError:
            # Loop is closed; sweep is shutting down. Drop the event.
            pass

    def close(self) -> None:
        """Signal end-of-stream by pushing the sentinel (None)."""
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, None)
        except RuntimeError:
            pass

    @property
    def queue(self) -> asyncio.Queue:
        return self._queue
