# Engine Simulator GUI v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **For frontend tasks (M1-M9 in Phase M):** invoke `frontend-design` as a sub-skill on each component, briefing it with Section 5 (Visual Design Language) of `docs/superpowers/specs/2026-04-08-engine-sim-gui-v1-design.md` as the design brief. The reference points are Linear, Vercel, Cursor, and Bloomberg Terminal — NOT Material Design or generic SaaS dashboards.

**Goal:** Build a local-laptop GUI for the engine simulator that watches sweeps run live and shows polished post-hoc reports for past sweeps. The integration with the existing solver is via the `EventConsumer` protocol from the parallelization work; zero changes to solver code.

**Architecture:** FastAPI backend serves a pre-built React+Tailwind frontend on `localhost:8765`. WebSocket pushes structured progress events from the solver to the browser in real time. A `SweepManager` owns the existing `ParallelSweepRunner` lifecycle; a `GUIEventConsumer` (implementing the existing `EventConsumer` protocol) bridges the solver's worker callback into an asyncio queue that the WebSocket pump drains. Sweeps auto-save to a `sweeps/` directory as self-contained JSON files.

**Tech Stack:** Python 3.9, FastAPI, uvicorn, websockets, pydantic, pytest, pytest-asyncio. React 18, TypeScript, Vite, TailwindCSS, Recharts, Zustand, lucide-react.

**Spec:** `docs/superpowers/specs/2026-04-08-engine-sim-gui-v1-design.md`

**Note on git:** This project is not currently a git repository. The "Save progress" steps below show the git commands you would run if it were. If git is not initialized, just check that no other tests have regressed before moving to the next task.

---

## File Structure

**New Python files (8 in `engine_simulator/gui/`):**

| Path | Responsibility |
|---|---|
| `engine_simulator/gui/__init__.py` | Package marker |
| `engine_simulator/gui/__main__.py` | `python -m engine_simulator.gui` entry point |
| `engine_simulator/gui/server.py` | FastAPI app, ASGI lifespan, browser launch |
| `engine_simulator/gui/routes_api.py` | REST endpoints |
| `engine_simulator/gui/routes_ws.py` | WebSocket `/ws/events` endpoint + connection registry |
| `engine_simulator/gui/sweep_manager.py` | `LiveSweepState` dataclass + `SweepManager` (owns sweep lifecycle) |
| `engine_simulator/gui/gui_event_consumer.py` | `GUIEventConsumer` (implements existing `EventConsumer` protocol) |
| `engine_simulator/gui/persistence.py` | `save_sweep`, `load_sweep`, atomic file writes, schema versioning |
| `engine_simulator/gui/snapshot.py` | Builds `LiveSweepState` → JSON snapshot for new WS connections |

**New Python test files (7 in `tests/`):**

| Path | Layer |
|---|---|
| `tests/test_gui_event_consumer.py` | 3 (plumbing) |
| `tests/test_gui_sweep_manager.py` | 3 (plumbing, with stub solver) |
| `tests/test_gui_persistence.py` | 2 (round-trip) |
| `tests/test_gui_snapshot.py` | 3 (plumbing) |
| `tests/test_gui_routes_api.py` | 3 (plumbing, FastAPI TestClient) |
| `tests/test_gui_routes_ws.py` | 3 (plumbing, FastAPI WebSocket TestClient) |
| `tests/test_gui_sweep_equivalence.py` | 1 (KEYSTONE: GUI bit-identical vs CLI) |

**New frontend files (~20 in `gui-frontend/`):**

| Path | Responsibility |
|---|---|
| `gui-frontend/package.json` | npm dependencies + build scripts |
| `gui-frontend/vite.config.ts` | Vite build config |
| `gui-frontend/tailwind.config.js` | Tailwind theme with spec colors + fonts |
| `gui-frontend/postcss.config.js` | PostCSS for Tailwind |
| `gui-frontend/tsconfig.json` | TypeScript config |
| `gui-frontend/index.html` | HTML entry point |
| `gui-frontend/src/main.tsx` | React entry, mounts `<App/>` |
| `gui-frontend/src/index.css` | Tailwind directives + global styles |
| `gui-frontend/src/App.tsx` | Top-level Mission Control layout |
| `gui-frontend/src/api/client.ts` | REST API wrappers |
| `gui-frontend/src/api/websocket.ts` | WebSocket connection + auto-reconnect |
| `gui-frontend/src/state/sweepStore.ts` | Zustand store for sweep state |
| `gui-frontend/src/state/eventReducer.ts` | Translates incoming events to state updates |
| `gui-frontend/src/types/events.ts` | TypeScript types matching the WS message schema |
| `gui-frontend/src/components/TopBar.tsx` | Run/Stop controls, status, file picker |
| `gui-frontend/src/components/RunSweepDialog.tsx` | Modal form to start a sweep |
| `gui-frontend/src/components/SweepCurves.tsx` | 6-chart grid (power/torque/VE/IMEP/plenum/restrictor) |
| `gui-frontend/src/components/WorkerTile.tsx` | One tile in the workers strip |
| `gui-frontend/src/components/WorkersStrip.tsx` | Horizontal grid of WorkerTiles |
| `gui-frontend/src/components/RpmDetail.tsx` | Bottom panel with cylinder/pipe/plenum tabs |
| `gui-frontend/src/components/CylinderTraces.tsx` | Cylinders tab content |
| `gui-frontend/src/components/PvDiagrams.tsx` | P-V tab content |
| `gui-frontend/src/components/PipeTraces.tsx` | Pipes tab content |
| `gui-frontend/src/components/PlenumPanel.tsx` | Plenum tab content |
| `gui-frontend/src/components/RestrictorPanel.tsx` | Restrictor tab content |
| `gui-frontend/src/components/CycleConvergencePanel.tsx` | Cycle convergence tab content |
| `gui-frontend/src/components/SweepListSidebar.tsx` | Right-edge collapsible list of past sweeps |
| `gui-frontend/src/components/charts/LineChart.tsx` | Reusable themed line chart wrapper |
| `gui-frontend/src/components/charts/Sparkline.tsx` | Tiny inline sparkline |

**New infrastructure files:**

| Path | Responsibility |
|---|---|
| `scripts/build_gui.py` | Builds the React bundle and copies it into `engine_simulator/gui/static/` |
| `engine_simulator/gui/static/.gitkeep` | Placeholder so the directory exists in source control (or empty repo) |
| `sweeps/.gitkeep` | Placeholder so the auto-save directory exists |

**Modified files:**

| Path | Changes |
|---|---|
| `requirements.txt` | Add: `fastapi>=0.110`, `uvicorn[standard]>=0.27`, `pydantic>=2.5`, `websockets>=12`, `pytest-asyncio>=0.23` |

**Files NOT touched:**

- `engine_simulator/simulation/orchestrator.py`, `parallel_sweep.py`
- `engine_simulator/gas_dynamics/*`, `engine/*`, `boundaries/*`
- `engine_simulator/simulation/plenum.py`, `convergence.py`, `engine_cycle.py`
- `engine_simulator/postprocessing/*`
- `engine_simulator/main.py` (CLI)
- `_run_sweep.py`, `_run_sweep_fast.py` and other top-level driver scripts

---

## Phase A: Backend Skeleton (FastAPI app, /api/health, browser launch)

End of phase: `python -m engine_simulator.gui` starts a FastAPI server on `localhost:8765`, opens the default browser, and `curl http://localhost:8765/api/health` returns `{"status":"ok"}`.

### Task A1: Add Python dependencies and create the gui package skeleton

**Files:**
- Modify: `requirements.txt`
- Create: `engine_simulator/gui/__init__.py`
- Create: `engine_simulator/gui/__main__.py`
- Create: `engine_simulator/gui/server.py`
- Create: `engine_simulator/gui/static/.gitkeep` (empty file)
- Create: `sweeps/.gitkeep` (empty file)

- [ ] **Step 1: Add FastAPI/uvicorn/websockets/pydantic/pytest-asyncio to requirements.txt**

Read the current `requirements.txt` first. Replace it with:

```
numpy>=1.24
scipy>=1.10
matplotlib>=3.7
pytest>=7.0
fastapi>=0.110
uvicorn[standard]>=0.27
pydantic>=2.5
websockets>=12
pytest-asyncio>=0.23
```

- [ ] **Step 2: Install the new dependencies into the existing venv**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pip install -r requirements.txt 2>&1 | tail -10`
Expected: `Successfully installed fastapi-... uvicorn-... pydantic-... websockets-... pytest-asyncio-...` and existing packages already satisfied.

- [ ] **Step 3: Create the gui package marker file**

Create `engine_simulator/gui/__init__.py` containing a single comment:

```python
"""Engine simulator GUI v1 — local FastAPI server + React frontend."""
```

- [ ] **Step 4: Create empty placeholder directories**

Create empty file `engine_simulator/gui/static/.gitkeep`.
Create empty file `sweeps/.gitkeep`.

- [ ] **Step 5: Create server.py with a minimal FastAPI app**

Create `engine_simulator/gui/server.py`:

```python
"""FastAPI app for the engine simulator GUI.

Owns the FastAPI instance, the ASGI lifespan (which initializes the
SweepManager), and the browser launch helper. Imports route modules
for their side effect of registering endpoints.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


logger = logging.getLogger(__name__)


# Module-level singleton — set during the lifespan startup. Other modules
# (routes_api, routes_ws) import this to access the SweepManager.
sweep_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Asgi lifespan: starts the SweepManager on startup, cleans up on shutdown."""
    global sweep_manager
    # Import lazily to avoid circular imports during module load
    from engine_simulator.gui.sweep_manager import SweepManager
    import asyncio

    loop = asyncio.get_running_loop()
    sweeps_dir = str(Path(__file__).resolve().parents[2] / "sweeps")

    async def broadcast_placeholder(msg):
        """Replaced by routes_ws.broadcast once that module is loaded."""
        pass

    sweep_manager = SweepManager(
        loop=loop,
        sweeps_dir=sweeps_dir,
        broadcast_fn=broadcast_placeholder,
    )

    yield  # server runs here

    # Shutdown: stop any running sweep
    if sweep_manager.current is not None and sweep_manager.current.status == "running":
        await sweep_manager.stop_sweep()


def create_app() -> FastAPI:
    """Construct the FastAPI app with all routes registered."""
    app = FastAPI(
        title="Engine Simulator GUI",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Routes are registered by importing their modules. We do this here
    # rather than at module load to control the import order.
    from engine_simulator.gui import routes_api  # noqa: F401
    from engine_simulator.gui import routes_ws   # noqa: F401

    app.include_router(routes_api.router)
    app.include_router(routes_ws.router)

    # Static files: pre-built React bundle
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


def open_browser_after_delay(url: str, delay: float = 1.0):
    """Open the user's default browser to `url` after a short delay,
    so the server has time to bind the port first."""
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def main(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True):
    """Entry point: start uvicorn and (optionally) open the browser."""
    import uvicorn

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    url = f"http://{host}:{port}/"
    logger.info(f"Server starting on {url}")

    if open_browser:
        open_browser_after_delay(url)

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")
```

- [ ] **Step 6: Create __main__.py so `python -m engine_simulator.gui` works**

Create `engine_simulator/gui/__main__.py`:

```python
"""Allow running the GUI as a module: `python -m engine_simulator.gui`."""

import argparse

from engine_simulator.gui.server import main


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Engine Simulator GUI v1 — local FastAPI + React",
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765,
                        help="Port to bind (default: 8765)")
    parser.add_argument("--no-browser", action="store_true",
                        help="Don't auto-open the browser")

    args = parser.parse_args()
    main(host=args.host, port=args.port, open_browser=not args.no_browser)
```

- [ ] **Step 7: Save progress (skip if not using git)**

```bash
git add requirements.txt engine_simulator/gui/ sweeps/
git commit -m "feat(gui): add gui package skeleton and dependencies"
```

---

### Task A2: Add /api/health endpoint and verify the server starts

**Files:**
- Create: `engine_simulator/gui/routes_api.py`
- Create: `engine_simulator/gui/routes_ws.py` (empty stub for now)
- Create: `tests/test_gui_routes_api.py`

- [ ] **Step 1: Create the empty routes_ws.py stub so server.py imports succeed**

Create `engine_simulator/gui/routes_ws.py`:

```python
"""WebSocket route for the GUI. Stub in Phase A; implemented in Phase H."""

from fastapi import APIRouter

router = APIRouter()
```

- [ ] **Step 2: Write the failing test for /api/health**

Create `tests/test_gui_routes_api.py`:

```python
"""REST endpoint integration tests for the GUI server.

Uses FastAPI's TestClient. No real solver, no real browser.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from engine_simulator.gui.server import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


class TestHealth:
    def test_health_returns_ok(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_routes_api.py -v 2>&1 | tail -15`
Expected: `404` because the `/api/health` endpoint doesn't exist yet.

- [ ] **Step 4: Implement routes_api.py with the health endpoint**

Create `engine_simulator/gui/routes_api.py`:

```python
"""REST endpoints for the GUI server."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    """Liveness check."""
    return {"status": "ok"}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_routes_api.py -v 2>&1 | tail -10`
Expected: 1 passed.

- [ ] **Step 6: Manual smoke test the server**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m engine_simulator.gui --no-browser &` (background it).
Wait 2 seconds, then run: `curl -s http://127.0.0.1:8765/api/health`
Expected: `{"status":"ok"}`
Then kill the server: `kill %1`

- [ ] **Step 7: Save progress**

```bash
git add engine_simulator/gui/routes_api.py engine_simulator/gui/routes_ws.py tests/test_gui_routes_api.py
git commit -m "feat(gui): add /api/health endpoint and routes_api skeleton"
```

---

## Phase B: GUIEventConsumer

End of phase: `GUIEventConsumer` correctly drains progress events from a non-asyncio thread into an asyncio queue.

### Task B1: GUIEventConsumer with thread-safe queue puts

**Files:**
- Create: `engine_simulator/gui/gui_event_consumer.py`
- Create: `tests/test_gui_event_consumer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_gui_event_consumer.py`:

```python
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
```

- [ ] **Step 2: Add pytest-asyncio config to enable @pytest.mark.asyncio**

Check if `pytest.ini` or `pyproject.toml` exists at `/Users/nmurray/Developer/1d/`. If not, create `pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
```

This makes async test functions work without needing the `@pytest.mark.asyncio` decorator and avoids deprecation warnings.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_event_consumer.py -v 2>&1 | tail -20`
Expected: ImportError because `gui_event_consumer.py` doesn't exist yet.

- [ ] **Step 4: Implement GUIEventConsumer**

Create `engine_simulator/gui/gui_event_consumer.py`:

```python
"""GUIEventConsumer — bridges the parallel sweep runner's event stream
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_event_consumer.py -v 2>&1 | tail -15`
Expected: 4 passed.

- [ ] **Step 6: Save progress**

```bash
git add engine_simulator/gui/gui_event_consumer.py tests/test_gui_event_consumer.py pytest.ini
git commit -m "feat(gui): add GUIEventConsumer with thread-safe asyncio queue bridge"
```

---

## Phase C: SweepManager

End of phase: `SweepManager` can start and stop sweeps, drain events, and apply them to the live state. Real solver integration is in C4.

### Task C1: LiveSweepState dataclass and helpers

**Files:**
- Create: `engine_simulator/gui/sweep_manager.py` (initial: just LiveSweepState + helper functions)

- [ ] **Step 1: Create the initial sweep_manager.py with LiveSweepState**

Create `engine_simulator/gui/sweep_manager.py`:

```python
"""SweepManager — owns the lifecycle of a parallel sweep for the GUI.

Wraps the existing ParallelSweepRunner with an asyncio-friendly facade:
- start_sweep() kicks off a sweep in a background thread
- A drain task pulls events from the GUIEventConsumer's queue and
  updates LiveSweepState
- On completion, save_sweep() persists the result to disk
- stop_sweep() cancels the sweep and kills worker processes
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _make_sweep_id(params: dict) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    return (
        f"{ts}_{int(params['rpm_start'])}-{int(params['rpm_end'])}"
        f"_step{int(params['rpm_step'])}_{params['n_cycles']}cyc"
    )


@dataclass
class LiveSweepState:
    """Single source of truth for the currently-running (or last-finished) sweep.

    Mutated by the event drain task as events arrive. Read by the WebSocket
    snapshot endpoint, the REST endpoints, and the persistence layer.
    """
    sweep_id: str
    status: str                                  # "running" | "complete" | "error" | "stopped"
    config: Any                                  # EngineConfig instance
    config_name: str
    rpm_points: list                             # list[float]
    n_cycles: int
    n_workers: int
    started_at: str                              # ISO timestamp
    completed_at: Optional[str] = None
    rpms: dict = field(default_factory=dict)     # rpm (float) -> per-rpm state dict
    results_by_rpm: dict = field(default_factory=dict)   # rpm (float) -> SimulationResults
    sweep_results: list = field(default_factory=list)    # ordered list of perf dicts
    error_msg: Optional[str] = None
    error_traceback: Optional[str] = None
```

- [ ] **Step 2: Verify the file imports cleanly**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -c "from engine_simulator.gui.sweep_manager import LiveSweepState, _make_sweep_id, _iso_now; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Save progress**

```bash
git add engine_simulator/gui/sweep_manager.py
git commit -m "feat(gui): add LiveSweepState dataclass"
```

---

### Task C2: SweepManager._apply_event with tests

**Files:**
- Modify: `engine_simulator/gui/sweep_manager.py`
- Create: `tests/test_gui_sweep_manager.py`

- [ ] **Step 1: Write failing tests for _apply_event**

Create `tests/test_gui_sweep_manager.py`:

```python
"""SweepManager unit tests.

C2 covers _apply_event in isolation. Later tasks add integration tests
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_sweep_manager.py -v 2>&1 | tail -20`
Expected: AttributeError because `SweepManager` class and `_apply_event` method don't exist yet.

- [ ] **Step 3: Add SweepManager class with __init__ and _apply_event**

Append to `engine_simulator/gui/sweep_manager.py` (after the `LiveSweepState` dataclass):

```python


class SweepManager:
    """Owns sweep lifecycle for the GUI: start, stop, drain events, save."""

    def __init__(self, loop, sweeps_dir: str, broadcast_fn):
        self._loop = loop
        self._sweeps_dir = sweeps_dir
        self._broadcast_fn = broadcast_fn
        self._current: Optional[LiveSweepState] = None
        self._sweep_task: Optional[asyncio.Task] = None
        self._drain_task: Optional[asyncio.Task] = None
        self._consumer = None
        # ParallelSweepRunner.run() is blocking. We run it in a single
        # thread so the asyncio loop stays responsive. The runner internally
        # spawns the actual ProcessPoolExecutor for the workers.
        self._runner_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="sweep-runner",
        )

    @property
    def current(self) -> Optional[LiveSweepState]:
        return self._current

    def _apply_event(self, event):
        """Mutate self._current.rpms based on the event type.

        Called from the drain task on the asyncio loop. Pure state mutation —
        broadcasting is done separately by the caller.
        """
        from engine_simulator.simulation.parallel_sweep import (
            ConvergedEvent, CycleDoneEvent, RPMDoneEvent,
            RPMErrorEvent, RPMStartEvent,
        )

        rpm = float(event.rpm)
        if rpm not in self._current.rpms:
            # Unknown RPM (shouldn't happen). Skip silently.
            return
        rpm_state = self._current.rpms[rpm]

        if isinstance(event, RPMStartEvent):
            rpm_state.update({
                "status": "running",
                "current_cycle": 0,
                "rpm_index": event.rpm_index,
                "delta_history": [],
                "p_ivc_history": [],
                "step_count": 0,
                "elapsed": 0.0,
            })
        elif isinstance(event, CycleDoneEvent):
            rpm_state["current_cycle"] = event.cycle
            rpm_state["delta"] = event.delta
            rpm_state.setdefault("delta_history", []).append(event.delta)
            rpm_state.setdefault("p_ivc_history", []).append(list(event.p_ivc))
            rpm_state["step_count"] = event.step_count
            rpm_state["elapsed"] = event.elapsed
        elif isinstance(event, ConvergedEvent):
            rpm_state["converged_at_cycle"] = event.cycle
        elif isinstance(event, RPMDoneEvent):
            rpm_state.update({
                "status": "done",
                "perf": event.perf,
                "elapsed": event.elapsed,
                "step_count": event.step_count,
                "converged": event.converged,
            })
        elif isinstance(event, RPMErrorEvent):
            rpm_state.update({
                "status": "error",
                "error_type": event.error_type,
                "error_msg": event.error_msg,
                "traceback": event.traceback,
            })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_sweep_manager.py::TestApplyEvent -v 2>&1 | tail -15`
Expected: 5 passed.

- [ ] **Step 5: Save progress**

```bash
git add engine_simulator/gui/sweep_manager.py tests/test_gui_sweep_manager.py
git commit -m "feat(gui): add SweepManager with _apply_event and LiveSweepState"
```

---

### Task C3: SweepManager.start_sweep / drain_events / stop_sweep with stub solver

**Files:**
- Modify: `engine_simulator/gui/sweep_manager.py`
- Modify: `tests/test_gui_sweep_manager.py`

- [ ] **Step 1: Write the failing tests for sweep lifecycle with a stub solver**

Append to `tests/test_gui_sweep_manager.py`:

```python


class TestSweepLifecycleStub:
    """Lifecycle tests using a stub _run_sweep_blocking that doesn't
    actually call the solver. The Layer 1 equivalence test in Phase D
    covers the real-solver integration."""

    @pytest.mark.asyncio
    async def test_start_sweep_creates_running_state(self, monkeypatch, tmp_path):
        from engine_simulator.gui.sweep_manager import SweepManager

        # Stub _run_sweep_blocking to do nothing (we just want to test
        # that start_sweep transitions state correctly)
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

        # Stub EngineConfig loading
        from unittest.mock import MagicMock
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
        from engine_simulator.gui.sweep_manager import SweepManager

        async def fake_broadcast(msg): pass
        loop = asyncio.get_running_loop()
        manager = SweepManager(loop, str(tmp_path), fake_broadcast)

        # Hand-craft a running state
        from engine_simulator.gui.sweep_manager import LiveSweepState
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
        from engine_simulator.gui.sweep_manager import SweepManager
        from engine_simulator.gui.gui_event_consumer import GUIEventConsumer

        broadcast_log = []
        async def fake_broadcast(msg):
            broadcast_log.append(msg)

        loop = asyncio.get_running_loop()
        manager = SweepManager(loop, str(tmp_path), fake_broadcast)

        # Hand-build state and consumer (skipping start_sweep)
        from engine_simulator.gui.sweep_manager import LiveSweepState
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_sweep_manager.py::TestSweepLifecycleStub -v 2>&1 | tail -25`
Expected: AttributeError or ImportError for missing methods (`start_sweep`, `_drain_events`, `_run_sweep_blocking`, `_run_sweep_in_thread`, etc.) and missing imports (`save_sweep`, `load_config`).

- [ ] **Step 3: Add the lifecycle methods + helper imports to SweepManager**

Append to `engine_simulator/gui/sweep_manager.py` AFTER the `_apply_event` method (before the class ends):

```python

    def _event_to_json(self, event):
        """Translate a Python event dataclass to a JSON-serializable dict."""
        from engine_simulator.simulation.parallel_sweep import (
            ConvergedEvent, CycleDoneEvent, RPMDoneEvent,
            RPMErrorEvent, RPMStartEvent,
        )

        if isinstance(event, RPMStartEvent):
            return {
                "type": "rpm_start", "rpm": event.rpm,
                "rpm_index": event.rpm_index,
                "n_cycles_target": event.n_cycles_target, "ts": event.ts,
            }
        elif isinstance(event, CycleDoneEvent):
            return {
                "type": "cycle_done", "rpm": event.rpm, "cycle": event.cycle,
                "delta": event.delta, "p_ivc": list(event.p_ivc),
                "step_count": event.step_count,
                "elapsed": event.elapsed, "ts": event.ts,
            }
        elif isinstance(event, ConvergedEvent):
            return {
                "type": "converged", "rpm": event.rpm,
                "cycle": event.cycle, "ts": event.ts,
            }
        elif isinstance(event, RPMDoneEvent):
            return {
                "type": "rpm_done", "rpm": event.rpm,
                "perf": _coerce_jsonable(event.perf),
                "elapsed": event.elapsed,
                "step_count": event.step_count,
                "converged": event.converged, "ts": event.ts,
                "results_available": True,
            }
        elif isinstance(event, RPMErrorEvent):
            return {
                "type": "rpm_error", "rpm": event.rpm,
                "error_type": event.error_type,
                "error_msg": event.error_msg,
                "traceback": event.traceback, "ts": event.ts,
            }
        return {"type": "unknown"}

    async def _drain_events(self):
        """Drain GUIEventConsumer.queue, apply state mutations, broadcast."""
        assert self._consumer is not None
        while True:
            event = await self._consumer.queue.get()
            if event is None:                # sentinel from .close()
                return
            self._apply_event(event)
            try:
                await self._broadcast_fn(self._event_to_json(event))
            except Exception:
                # Broadcast errors must not kill the drain task
                pass

    def _run_sweep_blocking(self, params: dict):
        """Synchronous: runs in the runner thread. Calls the existing
        SimulationOrchestrator unchanged."""
        from engine_simulator.simulation.orchestrator import (
            SimulationOrchestrator,
        )

        sim = SimulationOrchestrator(self._current.config)
        sweep_results = sim.run_rpm_sweep(
            rpm_start=params["rpm_start"],
            rpm_end=params["rpm_end"],
            rpm_step=params["rpm_step"],
            n_cycles=params["n_cycles"],
            verbose=False,
            n_workers=params["n_workers"],
            consumer=self._consumer,
        )
        self._current.sweep_results = sweep_results
        self._current.results_by_rpm = dict(sim.results_by_rpm)

    async def _run_sweep_in_thread(self, params: dict):
        """Run the sweep in a thread, then save and broadcast completion."""
        try:
            await self._loop.run_in_executor(
                self._runner_executor,
                self._run_sweep_blocking,
                params,
            )
            # The runner thread has returned. Wait for the drain task
            # to process any remaining events including the close sentinel.
            if self._drain_task is not None:
                try:
                    await asyncio.wait_for(self._drain_task, timeout=5.0)
                except asyncio.TimeoutError:
                    pass

            self._current.status = "complete"
            self._current.completed_at = _iso_now()

            filename = save_sweep(self._current, self._sweeps_dir)
            duration = self._compute_duration()
            await self._broadcast_fn({
                "type": "sweep_complete",
                "sweep_id": self._current.sweep_id,
                "filename": filename,
                "duration_seconds": duration,
            })
        except asyncio.CancelledError:
            self._current.status = "stopped"
            await self._broadcast_fn({
                "type": "sweep_complete",
                "sweep_id": self._current.sweep_id,
                "stopped": True,
            })
            raise
        except Exception as exc:
            import traceback
            self._current.status = "error"
            self._current.error_msg = str(exc)
            self._current.error_traceback = traceback.format_exc()
            await self._broadcast_fn({
                "type": "sweep_error",
                "error_msg": str(exc),
                "traceback": traceback.format_exc(),
            })

    def _compute_duration(self) -> float:
        from datetime import datetime
        try:
            start = datetime.fromisoformat(
                self._current.started_at.replace("Z", "+00:00")
            )
            end = datetime.fromisoformat(
                (self._current.completed_at or _iso_now()).replace("Z", "+00:00")
            )
            return (end - start).total_seconds()
        except Exception:
            return 0.0

    async def start_sweep(self, params: dict) -> str:
        """Start a sweep. Returns the sweep_id. Raises if one is already running."""
        if self._current is not None and self._current.status == "running":
            raise RuntimeError(
                "A sweep is already running. Stop it first."
            )

        config = load_config(_resolve_config_path(params["config_name"]))

        import numpy as np
        rpm_points = list(np.arange(
            params["rpm_start"],
            params["rpm_end"] + params["rpm_step"] / 2,
            params["rpm_step"],
        ))
        rpm_points = [float(r) for r in rpm_points]

        sweep_id = _make_sweep_id(params)
        self._current = LiveSweepState(
            sweep_id=sweep_id,
            status="running",
            config=config,
            config_name=params["config_name"],
            rpm_points=rpm_points,
            n_cycles=params["n_cycles"],
            n_workers=params["n_workers"],
            started_at=_iso_now(),
            rpms={
                float(rpm): {"status": "queued", "rpm_index": idx}
                for idx, rpm in enumerate(rpm_points)
            },
        )

        from engine_simulator.gui.gui_event_consumer import GUIEventConsumer
        self._consumer = GUIEventConsumer(self._loop)
        self._drain_task = asyncio.create_task(self._drain_events())
        self._sweep_task = asyncio.create_task(
            self._run_sweep_in_thread(params)
        )

        return sweep_id

    async def stop_sweep(self):
        """Cancel a running sweep. Idempotent."""
        if self._current is None or self._current.status != "running":
            return
        if self._sweep_task is not None and not self._sweep_task.done():
            self._sweep_task.cancel()
            try:
                await self._sweep_task
            except asyncio.CancelledError:
                pass
```

- [ ] **Step 4: Add the module-level helper functions and imports**

At the TOP of `engine_simulator/gui/sweep_manager.py`, add to the existing imports section (right after `from typing import Any, Optional`):

```python
from pathlib import Path


def _coerce_jsonable(obj):
    """Recursively coerce numpy scalars/arrays to plain Python types
    so the result is JSON-serializable."""
    import numpy as np
    if isinstance(obj, dict):
        return {str(k): _coerce_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_coerce_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer, np.bool_)):
        return obj.item()
    return obj


def _resolve_config_path(config_name: str) -> str:
    """Resolve a bare config name (e.g. 'cbr600rr.json') to a full
    path under engine_simulator/config/."""
    config_dir = (
        Path(__file__).resolve().parents[1] / "config"
    )
    return str(config_dir / config_name)


# Imported lazily inside SweepManager to avoid circular import at module load
def load_config(path):
    from engine_simulator.config.engine_config import load_config as _lc
    return _lc(path)


def save_sweep(state, sweeps_dir):
    from engine_simulator.gui.persistence import save_sweep as _ss
    return _ss(state, sweeps_dir)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_sweep_manager.py -v 2>&1 | tail -20`
Expected: All tests pass except possibly the ones requiring `save_sweep` (which uses persistence.py — that lives in Phase E). The `test_start_sweep_creates_running_state` test stubs `save_sweep` so it should pass. The `test_start_sweep_raises_if_already_running` test should pass. The `test_drain_task_processes_events_in_order` test should pass.

If `save_sweep` import fails because `persistence.py` doesn't exist yet, the lazy import inside `save_sweep()` won't trigger until that path is hit at runtime — and the stub test patches it. So all 3 tests should pass.

- [ ] **Step 6: Save progress**

```bash
git add engine_simulator/gui/sweep_manager.py tests/test_gui_sweep_manager.py
git commit -m "feat(gui): SweepManager start_sweep, drain_events, stop_sweep"
```

---

## Phase D: Layer 1 Numerical Equivalence Test (KEYSTONE)

End of phase: a sweep run via `SweepManager` produces bit-identical results to a CLI sweep with the same parameters. This test gates the rest of the work — if it doesn't pass, the GUI integration is wrong somewhere.

### Task D1: Layer 1 equivalence test

**Files:**
- Create: `tests/test_gui_sweep_equivalence.py`

- [ ] **Step 1: Write the equivalence test**

Create `tests/test_gui_sweep_equivalence.py`:

```python
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

from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator


# Use a small sweep so the test runs in reasonable time.
RPM_START = 8000
RPM_END = 10000
RPM_STEP = 1000
N_CYCLES = 4
N_WORKERS = 2


def _run_cli_sweep():
    config = EngineConfig()
    sim = SimulationOrchestrator(config)
    sweep = sim.run_rpm_sweep(
        rpm_start=RPM_START, rpm_end=RPM_END, rpm_step=RPM_STEP,
        n_cycles=N_CYCLES, verbose=False, n_workers=N_WORKERS,
    )
    return sweep


async def _run_gui_sweep(tmp_path):
    """Drive SweepManager directly with a fake broadcast fn."""
    from engine_simulator.gui.sweep_manager import SweepManager

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
        "config_name": "cbr600rr.json",
    }
    await manager.start_sweep(params)

    # Wait for the sweep to complete
    await asyncio.wait_for(manager._sweep_task, timeout=600)

    return manager.current.sweep_results, received_messages


class TestGuiSweepEquivalence:
    @pytest.mark.asyncio
    async def test_gui_sweep_matches_cli_bit_identical(self, tmp_path):
        cli_results = _run_cli_sweep()
        gui_results, _msgs = await _run_gui_sweep(tmp_path)

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
```

- [ ] **Step 2: Run the test**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_sweep_equivalence.py -v 2>&1 | tail -15`
Expected: PASS (takes ~5-10 minutes because it runs the real solver twice, 3 RPMs × 4 cycles each).

If the test fails:
- If it's a NameError or ImportError on `save_sweep`: skip this test for now (`@pytest.mark.skip`) and add it back after Phase E (Persistence) lands. The dependency is real because the GUI sweep path tries to call `save_sweep` on completion.
- Quick fix to unblock: temporarily monkey-patch `save_sweep` to a no-op in the test. Add this as the FIRST line of `_run_gui_sweep`:

  ```python
  from unittest.mock import patch
  with patch("engine_simulator.gui.sweep_manager.save_sweep",
             lambda state, sweeps_dir: "stub.json"):
      # ... rest of function body, indented by one level ...
  ```

  This is fine for D1 — Phase E will land persistence and we'll re-run the test without the patch.

- [ ] **Step 3: Save progress**

```bash
git add tests/test_gui_sweep_equivalence.py
git commit -m "test(gui): Layer 1 numerical equivalence (GUI vs CLI)"
```

---

## Phase E: Persistence

End of phase: sweeps auto-save to `sweeps/*.json` and can be loaded back with bit-identical data.

### Task E1: persistence.save_sweep with atomic file writes

**Files:**
- Create: `engine_simulator/gui/persistence.py`
- Create: `tests/test_gui_persistence.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_gui_persistence.py`:

```python
"""Sweep persistence round-trip tests.

Layer 2: a LiveSweepState saved to JSON and loaded back must produce
the same data. Catches schema bugs, dtype loss, and key-mismatch errors.
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest


def _build_sample_state(tmp_path):
    """Build a sample LiveSweepState resembling a real completed sweep."""
    from engine_simulator.gui.sweep_manager import LiveSweepState
    from engine_simulator.config.engine_config import EngineConfig
    from engine_simulator.postprocessing.results import SimulationResults, ProbeData

    cfg = EngineConfig()

    sample_results = SimulationResults()
    sample_results.theta_history = [0.0, 0.5, 1.0, 1.5]
    sample_results.dt_history = [0.0001, 0.0001, 0.0001, 0.0001]
    sample_results.plenum_pressure = [101325.0, 101300.0, 101280.0, 101290.0]
    sample_results.plenum_temperature = [300.0, 300.1, 300.2, 300.3]
    sample_results.restrictor_mdot = [0.012, 0.014, 0.013, 0.015]
    sample_results.restrictor_choked = [False, False, False, False]
    pd = ProbeData()
    pd.theta = [0.0, 0.5, 1.0, 1.5]
    pd.pressure = [101325.0, 101400.0, 101500.0, 101600.0]
    pd.temperature = [300.0, 300.1, 300.2, 300.3]
    pd.velocity = [0.0, 0.0, 0.0, 0.0]
    pd.density = [1.177, 1.179, 1.180, 1.181]
    sample_results.cylinder_data[0] = pd
    sample_results.pipe_probes["intake_runner_1_mid"] = pd

    state = LiveSweepState(
        sweep_id="2026-04-08T18-23-04_8000-8000_step1000_4cyc",
        status="complete",
        config=cfg,
        config_name="cbr600rr.json",
        rpm_points=[8000.0],
        n_cycles=4,
        n_workers=1,
        started_at="2026-04-08T18:23:04.123Z",
        completed_at="2026-04-08T18:24:11.847Z",
        rpms={
            8000.0: {
                "status": "done",
                "rpm_index": 0,
                "perf": {
                    "rpm": 8000.0,
                    "indicated_power_hp": 89.9,
                    "brake_power_hp": 72.2,
                    "brake_torque_Nm": 64.2,
                    "volumetric_efficiency_atm": 1.07,
                    "imep_bar": 16.78,
                    "bmep_bar": 13.47,
                    "wheel_power_hp": 72.2,
                    "wheel_torque_Nm": 64.2,
                    "drivetrain_efficiency": 1.0,
                    "indicated_power_kW": 67.05,
                    "indicated_torque_Nm": 80.04,
                    "brake_power_kW": 53.82,
                    "fmep_bar": 3.31,
                    "volumetric_efficiency_plenum": 1.28,
                    "volumetric_efficiency": 1.28,
                    "intake_mass_per_cycle_g": 0.756,
                    "restrictor_choked": False,
                    "restrictor_mdot": 0.054,
                    "plenum_pressure_bar": 0.85,
                },
                "elapsed": 11.2,
                "step_count": 4523,
                "converged": True,
            }
        },
        results_by_rpm={8000.0: sample_results},
        sweep_results=[
            {
                "rpm": 8000.0,
                "indicated_power_hp": 89.9,
                "brake_power_hp": 72.2,
                "brake_torque_Nm": 64.2,
                "volumetric_efficiency_atm": 1.07,
                "imep_bar": 16.78,
                "bmep_bar": 13.47,
                "wheel_power_hp": 72.2,
                "wheel_torque_Nm": 64.2,
                "drivetrain_efficiency": 1.0,
                "indicated_power_kW": 67.05,
                "indicated_torque_Nm": 80.04,
                "brake_power_kW": 53.82,
                "fmep_bar": 3.31,
                "volumetric_efficiency_plenum": 1.28,
                "volumetric_efficiency": 1.28,
                "intake_mass_per_cycle_g": 0.756,
                "restrictor_choked": False,
                "restrictor_mdot": 0.054,
                "plenum_pressure_bar": 0.85,
            }
        ],
    )
    return state


class TestSavePerfDicts:
    def test_save_creates_file(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep
        state = _build_sample_state(tmp_path)
        filename = save_sweep(state, str(tmp_path))
        path = Path(tmp_path) / filename
        assert path.exists()

    def test_save_filename_matches_schema(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep
        state = _build_sample_state(tmp_path)
        filename = save_sweep(state, str(tmp_path))
        assert filename.endswith(".json")
        assert "_8000-8000_step1000_4cyc" in filename

    def test_saved_file_has_schema_version(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep
        state = _build_sample_state(tmp_path)
        filename = save_sweep(state, str(tmp_path))
        with open(Path(tmp_path) / filename) as f:
            data = json.load(f)
        assert data["schema_version"] == 1

    def test_saved_file_has_metadata(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep
        state = _build_sample_state(tmp_path)
        filename = save_sweep(state, str(tmp_path))
        with open(Path(tmp_path) / filename) as f:
            data = json.load(f)
        assert data["metadata"]["config_name"] == "cbr600rr.json"
        assert data["metadata"]["n_workers_requested"] == 1
        assert "started_at" in data["metadata"]

    def test_saved_perf_dict_matches_input(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep
        state = _build_sample_state(tmp_path)
        filename = save_sweep(state, str(tmp_path))
        with open(Path(tmp_path) / filename) as f:
            data = json.load(f)
        assert data["perf"][0]["brake_power_hp"] == 72.2
        assert data["perf"][0]["rpm"] == 8000.0

    def test_atomic_write_no_temp_file_left_behind(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep
        state = _build_sample_state(tmp_path)
        save_sweep(state, str(tmp_path))
        tmp_files = list(Path(tmp_path).glob("*.tmp"))
        assert tmp_files == [], f"Stale .tmp file: {tmp_files}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_persistence.py::TestSavePerfDicts -v 2>&1 | tail -15`
Expected: ImportError because `persistence.py` doesn't exist yet.

- [ ] **Step 3: Implement persistence.py with save_sweep**

Create `engine_simulator/gui/persistence.py`:

```python
"""Sweep persistence — save/load LiveSweepState as JSON files in sweeps/.

The file format is a single JSON document per sweep with metadata,
parameters, the engine config snapshot, the perf dict list, and the
per-RPM SimulationResults arrays. See the v1 GUI design spec, Section 6.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from engine_simulator.gui.sweep_manager import LiveSweepState


SCHEMA_VERSION = 1


def _coerce_jsonable(obj):
    """Recursively coerce numpy scalars/arrays to plain Python."""
    if isinstance(obj, dict):
        return {str(k): _coerce_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_coerce_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer, np.bool_)):
        return obj.item()
    return obj


def _serialize_results(results) -> dict:
    """Convert a SimulationResults instance to a JSON-friendly dict."""
    return {
        "theta_history": _coerce_jsonable(results.theta_history),
        "dt_history": _coerce_jsonable(results.dt_history),
        "plenum_pressure": _coerce_jsonable(results.plenum_pressure),
        "plenum_temperature": _coerce_jsonable(results.plenum_temperature),
        "restrictor_mdot": _coerce_jsonable(results.restrictor_mdot),
        "restrictor_choked": _coerce_jsonable(results.restrictor_choked),
        "cylinder_data": {
            str(cid): {
                "theta": _coerce_jsonable(pd.theta),
                "pressure": _coerce_jsonable(pd.pressure),
                "temperature": _coerce_jsonable(pd.temperature),
                "velocity": _coerce_jsonable(pd.velocity),
                "density": _coerce_jsonable(pd.density),
            }
            for cid, pd in results.cylinder_data.items()
        },
        "pipe_probes": {
            name: {
                "theta": _coerce_jsonable(pd.theta),
                "pressure": _coerce_jsonable(pd.pressure),
                "temperature": _coerce_jsonable(pd.temperature),
                "velocity": _coerce_jsonable(pd.velocity),
                "density": _coerce_jsonable(pd.density),
            }
            for name, pd in results.pipe_probes.items()
        },
    }


def _build_filename(state: "LiveSweepState") -> str:
    """Build the schema filename for a saved sweep."""
    # state.sweep_id already follows the schema
    return f"{state.sweep_id}.json"


def save_sweep(state: "LiveSweepState", sweeps_dir: str) -> str:
    """Save a LiveSweepState to a JSON file in sweeps_dir.

    Writes atomically: first to <name>.tmp, then renames to <name>.
    Returns the filename (not the full path).
    """
    sweeps_path = Path(sweeps_dir)
    sweeps_path.mkdir(parents=True, exist_ok=True)

    filename = _build_filename(state)
    full_path = sweeps_path / filename
    tmp_path = sweeps_path / f"{filename}.tmp"

    duration = 0.0
    if state.completed_at and state.started_at:
        from datetime import datetime
        try:
            start = datetime.fromisoformat(state.started_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(state.completed_at.replace("Z", "+00:00"))
            duration = (end - start).total_seconds()
        except Exception:
            duration = 0.0

    document = {
        "schema_version": SCHEMA_VERSION,
        "sweep_id": state.sweep_id,
        "metadata": {
            "started_at": state.started_at,
            "completed_at": state.completed_at,
            "duration_seconds": duration,
            "host": socket.gethostname(),
            "python_version": sys.version.split()[0],
            "n_workers_requested": state.n_workers,
            "n_workers_effective": state.n_workers,
            "config_name": state.config_name,
            "git_status": None,
        },
        "sweep_params": {
            "rpm_start": state.rpm_points[0] if state.rpm_points else 0,
            "rpm_end": state.rpm_points[-1] if state.rpm_points else 0,
            "rpm_step": (
                state.rpm_points[1] - state.rpm_points[0]
                if len(state.rpm_points) > 1 else 0
            ),
            "n_cycles": state.n_cycles,
            "rpm_points": _coerce_jsonable(state.rpm_points),
        },
        "engine_config": _coerce_jsonable(asdict(state.config)),
        "perf": _coerce_jsonable(state.sweep_results),
        "results_by_rpm": {
            str(rpm): _serialize_results(results)
            for rpm, results in state.results_by_rpm.items()
        },
    }

    with open(tmp_path, "w") as f:
        json.dump(document, f)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp_path, full_path)
    return filename
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_persistence.py::TestSavePerfDicts -v 2>&1 | tail -15`
Expected: 6 passed.

- [ ] **Step 5: Save progress**

```bash
git add engine_simulator/gui/persistence.py tests/test_gui_persistence.py
git commit -m "feat(gui): persistence.save_sweep with atomic writes"
```

---

### Task E2: persistence.load_sweep + round-trip + schema/error handling

**Files:**
- Modify: `engine_simulator/gui/persistence.py`
- Modify: `tests/test_gui_persistence.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gui_persistence.py`:

```python


class TestLoadSweep:
    def test_load_returns_loaded_sweep_state(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep, load_sweep
        state = _build_sample_state(tmp_path)
        filename = save_sweep(state, str(tmp_path))
        loaded = load_sweep(str(Path(tmp_path) / filename))
        assert loaded.sweep_id == state.sweep_id
        assert len(loaded.sweep_results) == 1

    def test_save_load_roundtrip_perf_dicts_bit_identical(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep, load_sweep
        state = _build_sample_state(tmp_path)
        filename = save_sweep(state, str(tmp_path))
        loaded = load_sweep(str(Path(tmp_path) / filename))
        assert len(loaded.sweep_results) == len(state.sweep_results)
        for orig, lod in zip(state.sweep_results, loaded.sweep_results):
            for k in orig:
                assert orig[k] == lod[k], f"Mismatch on {k}"

    def test_save_load_roundtrip_results_arrays_match(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep, load_sweep
        state = _build_sample_state(tmp_path)
        filename = save_sweep(state, str(tmp_path))
        loaded = load_sweep(str(Path(tmp_path) / filename))
        for rpm in state.results_by_rpm:
            orig_r = state.results_by_rpm[rpm]
            lod_r = loaded.results_by_rpm[rpm]
            np.testing.assert_array_equal(
                np.asarray(orig_r.theta_history),
                np.asarray(lod_r.theta_history),
            )
            np.testing.assert_array_equal(
                np.asarray(orig_r.plenum_pressure),
                np.asarray(lod_r.plenum_pressure),
            )
            assert set(orig_r.cylinder_data.keys()) == set(
                lod_r.cylinder_data.keys()
            )
            for cid in orig_r.cylinder_data:
                np.testing.assert_array_equal(
                    np.asarray(orig_r.cylinder_data[cid].pressure),
                    np.asarray(lod_r.cylinder_data[cid].pressure),
                )

    def test_load_unknown_schema_version_raises(self, tmp_path):
        from engine_simulator.gui.persistence import load_sweep
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({
            "schema_version": 999,
            "sweep_id": "x", "metadata": {}, "sweep_params": {},
            "engine_config": {}, "perf": [], "results_by_rpm": {},
        }))
        with pytest.raises(ValueError, match="schema version"):
            load_sweep(str(bad))

    def test_load_corrupt_json_raises_clear_error(self, tmp_path):
        from engine_simulator.gui.persistence import load_sweep
        corrupt = tmp_path / "corrupt.json"
        corrupt.write_text("{not valid json")
        with pytest.raises(ValueError, match="Could not parse"):
            load_sweep(str(corrupt))


class TestListSweeps:
    def test_list_sweeps_returns_summaries(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep, list_sweeps
        state = _build_sample_state(tmp_path)
        save_sweep(state, str(tmp_path))
        summaries = list_sweeps(str(tmp_path))
        assert len(summaries) == 1
        assert summaries[0]["id"] == state.sweep_id

    def test_list_sweeps_empty_directory(self, tmp_path):
        from engine_simulator.gui.persistence import list_sweeps
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        assert list_sweeps(str(empty_dir)) == []

    def test_list_sweeps_skips_non_json_files(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep, list_sweeps
        state = _build_sample_state(tmp_path)
        save_sweep(state, str(tmp_path))
        (tmp_path / "readme.txt").write_text("not a sweep")
        (tmp_path / "junk.tmp").write_text("not a sweep")
        summaries = list_sweeps(str(tmp_path))
        assert len(summaries) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_persistence.py::TestLoadSweep tests/test_gui_persistence.py::TestListSweeps -v 2>&1 | tail -20`
Expected: ImportError for `load_sweep` and `list_sweeps`.

- [ ] **Step 3: Add load_sweep, list_sweeps, and the LoadedSweepState helper**

Append to `engine_simulator/gui/persistence.py`:

```python


def _deserialize_results(d: dict):
    """Convert a JSON dict back into a SimulationResults instance."""
    from engine_simulator.postprocessing.results import SimulationResults, ProbeData

    results = SimulationResults()
    results.theta_history = list(d.get("theta_history", []))
    results.dt_history = list(d.get("dt_history", []))
    results.plenum_pressure = list(d.get("plenum_pressure", []))
    results.plenum_temperature = list(d.get("plenum_temperature", []))
    results.restrictor_mdot = list(d.get("restrictor_mdot", []))
    results.restrictor_choked = list(d.get("restrictor_choked", []))

    for cid_str, probe_dict in d.get("cylinder_data", {}).items():
        pd = ProbeData()
        pd.theta = list(probe_dict.get("theta", []))
        pd.pressure = list(probe_dict.get("pressure", []))
        pd.temperature = list(probe_dict.get("temperature", []))
        pd.velocity = list(probe_dict.get("velocity", []))
        pd.density = list(probe_dict.get("density", []))
        results.cylinder_data[int(cid_str)] = pd

    for name, probe_dict in d.get("pipe_probes", {}).items():
        pd = ProbeData()
        pd.theta = list(probe_dict.get("theta", []))
        pd.pressure = list(probe_dict.get("pressure", []))
        pd.temperature = list(probe_dict.get("temperature", []))
        pd.velocity = list(probe_dict.get("velocity", []))
        pd.density = list(probe_dict.get("density", []))
        results.pipe_probes[name] = pd

    return results


def load_sweep(file_path: str):
    """Load a sweep file from disk into a LoadedSweepState.

    Raises ValueError on parse errors or unknown schema versions.
    """
    try:
        with open(file_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Could not parse {file_path}: {exc}"
        ) from exc
    except FileNotFoundError as exc:
        raise ValueError(f"Sweep file not found: {file_path}") from exc

    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"Sweep file uses schema version {version}, "
            f"this version of the GUI supports up to {SCHEMA_VERSION}. "
            f"Update the GUI or use an older sweep."
        )

    # Lazy import to avoid circular import at module load
    from engine_simulator.gui.sweep_manager import LiveSweepState

    rpm_points = data["sweep_params"].get("rpm_points", [])
    results_by_rpm = {
        float(rpm): _deserialize_results(rd)
        for rpm, rd in data.get("results_by_rpm", {}).items()
    }

    state = LiveSweepState(
        sweep_id=data["sweep_id"],
        status="complete",
        config=data["engine_config"],   # raw dict, not reconstructed EngineConfig
        config_name=data["metadata"].get("config_name", ""),
        rpm_points=[float(r) for r in rpm_points],
        n_cycles=data["sweep_params"].get("n_cycles", 0),
        n_workers=data["metadata"].get("n_workers_effective", 0),
        started_at=data["metadata"].get("started_at", ""),
        completed_at=data["metadata"].get("completed_at"),
        rpms={
            float(p["rpm"]): {
                "status": "done",
                "rpm_index": idx,
                "perf": p,
            }
            for idx, p in enumerate(data.get("perf", []))
        },
        results_by_rpm=results_by_rpm,
        sweep_results=data.get("perf", []),
    )
    return state


def list_sweeps(sweeps_dir: str) -> list:
    """List the saved sweeps in sweeps_dir, newest first.

    Returns a list of summary dicts (id, filename, started_at, etc.)
    suitable for the GUI's "available sweeps" dropdown.
    """
    sweeps_path = Path(sweeps_dir)
    if not sweeps_path.exists():
        return []

    summaries = []
    for path in sorted(sweeps_path.glob("*.json"), reverse=True):
        if path.name.endswith(".tmp"):
            continue
        try:
            with open(path) as f:
                data = json.load(f)
            rpm_points = data.get("sweep_params", {}).get("rpm_points", [])
            summaries.append({
                "id": data.get("sweep_id", path.stem),
                "filename": path.name,
                "started_at": data.get("metadata", {}).get("started_at", ""),
                "duration_seconds": data.get("metadata", {}).get(
                    "duration_seconds", 0.0
                ),
                "rpm_range": [
                    rpm_points[0] if rpm_points else 0,
                    rpm_points[-1] if rpm_points else 0,
                ],
                "n_rpm_points": len(rpm_points),
            })
        except Exception:
            # Skip unparseable files silently
            continue
    return summaries
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_persistence.py -v 2>&1 | tail -20`
Expected: All persistence tests pass (6 from TestSavePerfDicts + 5 from TestLoadSweep + 3 from TestListSweeps = 14 total).

- [ ] **Step 5: Re-run the equivalence test from D1 (without the save_sweep stub now that persistence exists)**

If you added a `with patch(...)` block to `test_gui_sweep_equivalence.py` in D1, remove it now.

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_sweep_equivalence.py -v 2>&1 | tail -10`
Expected: PASS (the GUI sweep now writes a file to `tmp_path/<filename>.json` on completion, so the test should still pass).

- [ ] **Step 6: Save progress**

```bash
git add engine_simulator/gui/persistence.py tests/test_gui_persistence.py tests/test_gui_sweep_equivalence.py
git commit -m "feat(gui): persistence.load_sweep, list_sweeps, schema versioning"
```

---

## Phase F: REST routes (configs, sweeps, results)

End of phase: all REST endpoints from spec Section 3 are implemented and tested.

### Task F1: /api/configs and /api/sweeps endpoints

**Files:**
- Modify: `engine_simulator/gui/routes_api.py`
- Modify: `tests/test_gui_routes_api.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_gui_routes_api.py`:

```python


class TestConfigsEndpoint:
    def test_list_configs_returns_cbr600rr(self, client):
        response = client.get("/api/configs")
        assert response.status_code == 200
        configs = response.json()
        assert any(c["name"] == "cbr600rr.json" for c in configs)


class TestSweepsListEndpoint:
    def test_empty_sweeps_returns_empty_list(self, client, monkeypatch, tmp_path):
        from engine_simulator.gui import routes_api as ra
        monkeypatch.setattr(ra, "get_sweeps_dir", lambda: str(tmp_path))
        response = client.get("/api/sweeps")
        assert response.status_code == 200
        assert response.json() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_routes_api.py::TestConfigsEndpoint tests/test_gui_routes_api.py::TestSweepsListEndpoint -v 2>&1 | tail -10`
Expected: 404 for both endpoints.

- [ ] **Step 3: Add the endpoints**

Replace the contents of `engine_simulator/gui/routes_api.py` with:

```python
"""REST endpoints for the GUI server."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api")


# Default directory resolvers — overridable in tests via monkeypatch
def get_configs_dir() -> str:
    return str(Path(__file__).resolve().parents[1] / "config")


def get_sweeps_dir() -> str:
    return str(Path(__file__).resolve().parents[2] / "sweeps")


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/configs")
async def list_configs():
    configs_dir = Path(get_configs_dir())
    if not configs_dir.exists():
        return []
    out = []
    for path in sorted(configs_dir.glob("*.json")):
        out.append({
            "name": path.name,
            "path": str(path),
            "summary": "",
        })
    return out


@router.get("/configs/{name}")
async def get_config(name: str):
    import json
    config_path = Path(get_configs_dir()) / name
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"Config not found: {name}")
    with open(config_path) as f:
        return json.load(f)


@router.get("/sweeps")
async def list_sweeps_endpoint():
    from engine_simulator.gui.persistence import list_sweeps
    return list_sweeps(get_sweeps_dir())


@router.get("/sweeps/{sweep_id}")
async def get_sweep(sweep_id: str):
    from engine_simulator.gui.persistence import load_sweep
    sweeps_dir = Path(get_sweeps_dir())
    file_path = sweeps_dir / f"{sweep_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Sweep not found: {sweep_id}")
    try:
        loaded = load_sweep(str(file_path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Return the raw JSON file content (we already validated it via load_sweep)
    import json
    with open(file_path) as f:
        return json.load(f)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_routes_api.py -v 2>&1 | tail -15`
Expected: All tests pass.

- [ ] **Step 5: Save progress**

```bash
git add engine_simulator/gui/routes_api.py tests/test_gui_routes_api.py
git commit -m "feat(gui): /api/configs and /api/sweeps endpoints"
```

---

### Task F2: /api/sweep/start, /api/sweep/stop, /api/sweeps/current/results/{rpm}

**Files:**
- Modify: `engine_simulator/gui/routes_api.py`
- Modify: `tests/test_gui_routes_api.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_gui_routes_api.py`:

```python


class TestSweepStartStop:
    def test_start_sweep_with_invalid_body_returns_422(self, client):
        # Missing required fields
        response = client.post("/api/sweep/start", json={})
        assert response.status_code == 422

    def test_start_sweep_with_no_manager_returns_500(self, client):
        # The sweep_manager singleton is None until lifespan startup runs.
        # TestClient triggers lifespan, so this should actually work — but
        # if it doesn't, we get a 500. This test is a guard against
        # accidentally bypassing lifespan setup.
        # We hit it with a valid body so the schema validates first.
        response = client.post("/api/sweep/start", json={
            "rpm_start": 8000, "rpm_end": 8000, "rpm_step": 1000,
            "n_cycles": 4, "n_workers": 1, "config_name": "cbr600rr.json",
        })
        # Either it works (200) or returns a meaningful error
        assert response.status_code in (200, 500, 503)

    def test_stop_sweep_when_idle_returns_200(self, client):
        response = client.post("/api/sweep/stop")
        assert response.status_code == 200
```

- [ ] **Step 2: Add the endpoints to routes_api.py**

Append to `engine_simulator/gui/routes_api.py`:

```python


class SweepStartParams(BaseModel):
    rpm_start: float = Field(..., gt=0)
    rpm_end: float = Field(..., gt=0)
    rpm_step: float = Field(..., gt=0)
    n_cycles: int = Field(..., gt=0, le=100)
    n_workers: int = Field(..., gt=0, le=64)
    config_name: str = Field(...)


@router.post("/sweep/start")
async def start_sweep(params: SweepStartParams):
    from engine_simulator.gui import server
    if server.sweep_manager is None:
        raise HTTPException(
            status_code=503,
            detail="Sweep manager not initialized",
        )
    try:
        sweep_id = await server.sweep_manager.start_sweep(params.dict())
    except RuntimeError as exc:
        # "Sweep already running"
        raise HTTPException(status_code=409, detail=str(exc))
    return {"sweep_id": sweep_id, "status": "running"}


@router.post("/sweep/stop")
async def stop_sweep():
    from engine_simulator.gui import server
    if server.sweep_manager is None:
        return {"status": "stopped"}
    await server.sweep_manager.stop_sweep()
    return {"status": "stopped"}


@router.get("/sweeps/current/results/{rpm}")
async def get_current_sweep_results(rpm: float):
    from engine_simulator.gui import server
    from engine_simulator.gui.persistence import _serialize_results

    if server.sweep_manager is None or server.sweep_manager.current is None:
        raise HTTPException(status_code=404, detail="No current sweep")

    state = server.sweep_manager.current
    results = state.results_by_rpm.get(float(rpm))
    if results is None:
        raise HTTPException(
            status_code=404,
            detail=f"No recorded results for RPM {rpm}",
        )
    return _serialize_results(results)
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_routes_api.py -v 2>&1 | tail -20`
Expected: All tests pass.

- [ ] **Step 4: Save progress**

```bash
git add engine_simulator/gui/routes_api.py tests/test_gui_routes_api.py
git commit -m "feat(gui): /api/sweep/start, /sweep/stop, /sweeps/current/results"
```

---

## Phase G: WebSocket route + snapshot builder

End of phase: a client connecting to `/ws/events` immediately receives a state snapshot and then receives broadcast events as the sweep progresses.

### Task G1: snapshot.py builder

**Files:**
- Create: `engine_simulator/gui/snapshot.py`
- Create: `tests/test_gui_snapshot.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_gui_snapshot.py`:

```python
"""Snapshot builder tests.

snapshot.build_snapshot translates a LiveSweepState (or None) into the
JSON-serializable dict that gets sent to a freshly connected WebSocket
client.
"""

import pytest
from unittest.mock import MagicMock


def test_snapshot_with_no_sweep(tmp_path):
    from engine_simulator.gui.snapshot import build_snapshot
    snap = build_snapshot(current=None, sweeps_dir=str(tmp_path))
    assert snap["type"] == "snapshot"
    assert snap["sweep"] is None
    assert snap["available_sweeps"] == []


def test_snapshot_with_running_sweep(tmp_path):
    from engine_simulator.gui.snapshot import build_snapshot
    from engine_simulator.gui.sweep_manager import LiveSweepState
    state = LiveSweepState(
        sweep_id="test_sweep",
        status="running",
        config=MagicMock(),
        config_name="cbr600rr.json",
        rpm_points=[8000.0, 10000.0],
        n_cycles=4,
        n_workers=2,
        started_at="2026-04-08T18:00:00Z",
        rpms={
            8000.0: {"status": "running", "rpm_index": 0, "current_cycle": 2,
                     "delta": 0.05, "delta_history": [0.1, 0.05],
                     "step_count": 1000, "elapsed": 5.0,
                     "p_ivc_history": [[95000.0]*4, [95100.0]*4]},
            10000.0: {"status": "queued", "rpm_index": 1},
        },
    )
    snap = build_snapshot(current=state, sweeps_dir=str(tmp_path))
    assert snap["sweep"] is not None
    assert snap["sweep"]["status"] == "running"
    assert snap["sweep"]["sweep_id"] == "test_sweep"
    assert snap["sweep"]["rpm_points"] == [8000.0, 10000.0]
    assert "8000.0" in snap["sweep"]["rpms"] or 8000.0 in snap["sweep"]["rpms"]
    assert snap["sweep"]["config_summary"]["n_cycles"] == 4


def test_snapshot_lists_available_sweeps_from_disk(tmp_path):
    from engine_simulator.gui.snapshot import build_snapshot
    from engine_simulator.gui.persistence import save_sweep
    from engine_simulator.gui.sweep_manager import LiveSweepState
    from engine_simulator.config.engine_config import EngineConfig

    state = LiveSweepState(
        sweep_id="2026-04-08T18-00-00_8000-8000_step1000_4cyc",
        status="complete",
        config=EngineConfig(),
        config_name="cbr600rr.json",
        rpm_points=[8000.0],
        n_cycles=4,
        n_workers=1,
        started_at="2026-04-08T18:00:00Z",
        completed_at="2026-04-08T18:01:00Z",
        sweep_results=[{"rpm": 8000.0, "brake_power_hp": 72.2}],
    )
    save_sweep(state, str(tmp_path))

    snap = build_snapshot(current=None, sweeps_dir=str(tmp_path))
    assert len(snap["available_sweeps"]) == 1
    assert snap["available_sweeps"][0]["id"] == state.sweep_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_snapshot.py -v 2>&1 | tail -15`
Expected: ImportError for `snapshot`.

- [ ] **Step 3: Implement snapshot.py**

Create `engine_simulator/gui/snapshot.py`:

```python
"""Build a JSON-serializable snapshot of the current sweep state.

Sent to every newly-connected WebSocket client so they can render the
in-progress (or last-finished) sweep without missing any events.
"""

from __future__ import annotations

from typing import Optional

from engine_simulator.gui.persistence import list_sweeps, _coerce_jsonable


def _serialize_rpms(rpms: dict) -> dict:
    out = {}
    for rpm, rpm_state in rpms.items():
        out[str(rpm)] = _coerce_jsonable(rpm_state)
    return out


def build_snapshot(current, sweeps_dir: str) -> dict:
    """Build a snapshot dict from the current LiveSweepState (or None).

    The result is the payload of a `snapshot` WebSocket message.
    """
    available = list_sweeps(sweeps_dir)

    if current is None:
        return {
            "type": "snapshot",
            "sweep": None,
            "available_sweeps": available,
        }

    rpm_points_list = list(current.rpm_points)
    rpm_step = (
        rpm_points_list[1] - rpm_points_list[0]
        if len(rpm_points_list) >= 2 else 0
    )

    sweep_payload = {
        "status": current.status,
        "sweep_id": current.sweep_id,
        "config_summary": {
            "rpm_start": rpm_points_list[0] if rpm_points_list else 0,
            "rpm_end": rpm_points_list[-1] if rpm_points_list else 0,
            "rpm_step": rpm_step,
            "n_cycles": current.n_cycles,
            "n_workers": current.n_workers,
            "config_name": current.config_name,
        },
        "rpm_points": _coerce_jsonable(rpm_points_list),
        "started_at": current.started_at,
        "elapsed_seconds": 0.0,   # filled in by caller if desired
        "rpms": _serialize_rpms(current.rpms),
        "results_by_rpm_summary": {
            str(rpm): {"available": True}
            for rpm in current.results_by_rpm.keys()
        },
    }

    return {
        "type": "snapshot",
        "sweep": sweep_payload,
        "available_sweeps": available,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_snapshot.py -v 2>&1 | tail -10`
Expected: 3 passed.

- [ ] **Step 5: Save progress**

```bash
git add engine_simulator/gui/snapshot.py tests/test_gui_snapshot.py
git commit -m "feat(gui): build_snapshot for WebSocket client reconnect"
```

---

### Task G2: WebSocket route with broadcast registry

**Files:**
- Modify: `engine_simulator/gui/routes_ws.py`
- Modify: `engine_simulator/gui/server.py` (replace broadcast_placeholder)
- Create: `tests/test_gui_routes_ws.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_gui_routes_ws.py`:

```python
"""WebSocket protocol tests using FastAPI's TestClient WebSocket support."""

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from engine_simulator.gui.server import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


class TestWebSocketSnapshot:
    def test_initial_snapshot_received_on_connect(self, client):
        with client.websocket_connect("/ws/events") as ws:
            data = ws.receive_json()
        assert data["type"] == "snapshot"
        assert "sweep" in data
        assert "available_sweeps" in data

    def test_snapshot_when_no_sweep_running_has_null_sweep(self, client):
        with client.websocket_connect("/ws/events") as ws:
            data = ws.receive_json()
        assert data["sweep"] is None

    def test_ping_pong_heartbeat(self, client):
        with client.websocket_connect("/ws/events") as ws:
            ws.receive_json()   # initial snapshot
            ws.send_json({"type": "ping"})
            response = ws.receive_json()
        assert response == {"type": "pong"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_routes_ws.py -v 2>&1 | tail -15`
Expected: Tests fail because `/ws/events` route doesn't exist yet.

- [ ] **Step 3: Implement routes_ws.py with the connection registry and broadcast**

Replace the contents of `engine_simulator/gui/routes_ws.py`:

```python
"""WebSocket route + connection registry + broadcast helper."""

from __future__ import annotations

import asyncio
import logging
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


logger = logging.getLogger(__name__)

router = APIRouter()


# Global set of active WebSocket connections. Each new client connection
# adds itself; disconnects remove themselves. broadcast() iterates the set.
_active_connections: Set[WebSocket] = set()
_connections_lock = asyncio.Lock()


async def broadcast(message: dict) -> None:
    """Send a message to every connected client.

    Errors on individual connections (e.g. client disconnected) are
    swallowed; the connection gets removed from the active set.
    """
    async with _connections_lock:
        to_remove = []
        for ws in _active_connections:
            try:
                await ws.send_json(message)
            except Exception:
                to_remove.append(ws)
        for ws in to_remove:
            _active_connections.discard(ws)


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """WebSocket endpoint: sends initial snapshot, then forwards broadcasts."""
    from engine_simulator.gui import server
    from engine_simulator.gui.snapshot import build_snapshot

    await websocket.accept()
    async with _connections_lock:
        _active_connections.add(websocket)

    try:
        # Send the initial snapshot
        current = (
            server.sweep_manager.current
            if server.sweep_manager is not None
            else None
        )
        sweeps_dir = (
            server.sweep_manager._sweeps_dir
            if server.sweep_manager is not None
            else "sweeps"
        )
        snapshot = build_snapshot(current, sweeps_dir)
        await websocket.send_json(snapshot)

        # Receive loop: handle pings; everything else is broadcast-driven
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error")
    finally:
        async with _connections_lock:
            _active_connections.discard(websocket)
```

- [ ] **Step 4: Hook routes_ws.broadcast into the server's lifespan as the SweepManager's broadcast_fn**

Edit `engine_simulator/gui/server.py`. Find the `lifespan` function and replace it with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """ASGI lifespan: starts the SweepManager on startup, cleans up on shutdown."""
    global sweep_manager
    from engine_simulator.gui.sweep_manager import SweepManager
    from engine_simulator.gui.routes_ws import broadcast
    import asyncio

    loop = asyncio.get_running_loop()
    sweeps_dir = str(Path(__file__).resolve().parents[2] / "sweeps")

    sweep_manager = SweepManager(
        loop=loop,
        sweeps_dir=sweeps_dir,
        broadcast_fn=broadcast,
    )

    yield  # server runs here

    # Shutdown: stop any running sweep
    if sweep_manager.current is not None and sweep_manager.current.status == "running":
        await sweep_manager.stop_sweep()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_routes_ws.py -v 2>&1 | tail -15`
Expected: 3 passed.

- [ ] **Step 6: Run the full test suite (no equivalence test) to verify nothing regressed**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_routes_api.py tests/test_gui_routes_ws.py tests/test_gui_event_consumer.py tests/test_gui_sweep_manager.py tests/test_gui_persistence.py tests/test_gui_snapshot.py -v 2>&1 | tail -20`
Expected: All tests pass.

- [ ] **Step 7: Save progress**

```bash
git add engine_simulator/gui/routes_ws.py engine_simulator/gui/server.py tests/test_gui_routes_ws.py
git commit -m "feat(gui): WebSocket route with snapshot broadcast"
```

---

## Phase H: Frontend Scaffold (Vite + React + Tailwind)

End of phase: `cd gui-frontend && npm run build` produces a `dist/` directory; `python scripts/build_gui.py` copies it into `engine_simulator/gui/static/`; the FastAPI server serves the React app at `http://localhost:8765/`.

### Task H1: gui-frontend project setup with package.json, vite, tailwind, tsconfig

**Files:**
- Create: `gui-frontend/package.json`
- Create: `gui-frontend/vite.config.ts`
- Create: `gui-frontend/tsconfig.json`
- Create: `gui-frontend/tsconfig.node.json`
- Create: `gui-frontend/index.html`
- Create: `gui-frontend/postcss.config.js`
- Create: `gui-frontend/tailwind.config.js`
- Create: `gui-frontend/src/main.tsx`
- Create: `gui-frontend/src/App.tsx` (placeholder)
- Create: `gui-frontend/src/index.css`
- Create: `gui-frontend/.gitignore`

- [ ] **Step 1: Verify Node.js is available**

Run: `node --version && npm --version`
Expected: Node 18+ and npm 9+.

If Node is not installed: stop and ask the user to install Node.js (e.g., via `brew install node` on macOS) before proceeding.

- [ ] **Step 2: Create gui-frontend/package.json**

Create `gui-frontend/package.json`:

```json
{
  "name": "engine-sim-gui-frontend",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "zustand": "^4.5.2",
    "recharts": "^2.12.7",
    "lucide-react": "^0.378.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38",
    "tailwindcss": "^3.4.4",
    "typescript": "^5.4.5",
    "vite": "^5.2.13"
  }
}
```

- [ ] **Step 3: Install npm dependencies**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm install 2>&1 | tail -10`
Expected: `added N packages` with no errors. May produce some peer dependency warnings; those are fine.

- [ ] **Step 4: Create vite.config.ts**

Create `gui-frontend/vite.config.ts`:

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/ws": {
        target: "ws://127.0.0.1:8765",
        ws: true,
      },
    },
  },
});
```

- [ ] **Step 5: Create TypeScript configs**

Create `gui-frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Create `gui-frontend/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 6: Create index.html**

Create `gui-frontend/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Engine Simulator GUI</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  </head>
  <body class="bg-bg text-text-primary">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Create the placeholder src/main.tsx and src/App.tsx**

Create `gui-frontend/src/main.tsx`:

```typescript
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

Create `gui-frontend/src/App.tsx`:

```typescript
export default function App() {
  return (
    <div className="min-h-screen flex items-center justify-center text-text-primary font-ui">
      <div className="text-center">
        <h1 className="text-3xl font-semibold mb-2">Engine Simulator GUI</h1>
        <p className="text-text-secondary">Phase H scaffold — components land in Phase J</p>
      </div>
    </div>
  );
}
```

- [ ] **Step 8: Create .gitignore in gui-frontend**

Create `gui-frontend/.gitignore`:

```
node_modules
dist
.DS_Store
*.local
```

- [ ] **Step 9: Save progress**

```bash
git add gui-frontend/package.json gui-frontend/vite.config.ts gui-frontend/tsconfig.json gui-frontend/tsconfig.node.json gui-frontend/index.html gui-frontend/src/main.tsx gui-frontend/src/App.tsx gui-frontend/.gitignore
git commit -m "feat(gui-frontend): vite + react + typescript scaffold"
```

---

### Task H2: Tailwind config with spec colors and fonts

**Files:**
- Create: `gui-frontend/postcss.config.js`
- Create: `gui-frontend/tailwind.config.js`
- Create: `gui-frontend/src/index.css`

- [ ] **Step 1: Create postcss.config.js**

Create `gui-frontend/postcss.config.js`:

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 2: Create tailwind.config.js with the spec's design tokens**

Create `gui-frontend/tailwind.config.js`:

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Spec section 5: Color palette
        bg: "#0A0A0B",
        surface: "#131316",
        "surface-raised": "#1A1A1F",
        "border-default": "#25252B",
        "border-emphasis": "#3A3A42",
        "text-primary": "#F5F5F7",
        "text-secondary": "#8B8B95",
        "text-muted": "#565660",
        accent: "#FF4F1F",
        "accent-dim": "#B33815",

        // Chart colors
        "chart-power-ind": "#E5484D",
        "chart-power-brk": "#4493F8",
        "chart-ve": "#3DD68C",
        "chart-restrictor": "#C586E8",

        // Status colors
        "status-queued": "#565660",
        "status-running": "#FF4F1F",
        "status-converged": "#FFD15C",
        "status-done": "#3DD68C",
        "status-error": "#E5484D",
      },
      fontFamily: {
        ui: ["'Inter Tight'", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "monospace"],
      },
      borderRadius: {
        DEFAULT: "4px",
        md: "6px",
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 3: Create src/index.css with Tailwind directives + global resets**

Create `gui-frontend/src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  html {
    font-family: 'Inter Tight', ui-sans-serif, system-ui, sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }
  body {
    background-color: #0A0A0B;
    color: #F5F5F7;
    font-feature-settings: "cv11", "ss01", "ss03";
  }
  /* Mono numeric values use tabular figures */
  .font-mono {
    font-feature-settings: "tnum";
  }
}
```

- [ ] **Step 4: Build the project to verify everything compiles**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -15`
Expected: Build completes successfully with output like `vite v5.2.13 building for production...` and `dist/index.html ... dist/assets/*.js dist/assets/*.css`. No errors.

- [ ] **Step 5: Save progress**

```bash
git add gui-frontend/postcss.config.js gui-frontend/tailwind.config.js gui-frontend/src/index.css
git commit -m "feat(gui-frontend): tailwind config with spec design tokens"
```

---

### Task H3: Build helper script + static file serving

**Files:**
- Create: `scripts/build_gui.py`

- [ ] **Step 1: Verify the scripts directory exists**

Run: `ls /Users/nmurray/Developer/1d/scripts/ 2>/dev/null || mkdir -p /Users/nmurray/Developer/1d/scripts`

- [ ] **Step 2: Create the build helper script**

Create `scripts/build_gui.py`:

```python
#!/usr/bin/env python3
"""Build the React frontend and copy the dist/ output into the Python package.

Usage:
    python scripts/build_gui.py

This runs `npm run build` in gui-frontend/, then copies the generated
dist/ contents into engine_simulator/gui/static/. The Python package
ships with the pre-built bundle inside it; end users don't need Node.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    frontend_dir = repo_root / "gui-frontend"
    dist_dir = frontend_dir / "dist"
    static_dir = repo_root / "engine_simulator" / "gui" / "static"

    if not frontend_dir.exists():
        print(f"ERROR: {frontend_dir} does not exist", file=sys.stderr)
        return 1

    print(f"Running 'npm run build' in {frontend_dir}...")
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(frontend_dir),
        check=False,
    )
    if result.returncode != 0:
        print("ERROR: npm build failed", file=sys.stderr)
        return result.returncode

    if not dist_dir.exists():
        print(f"ERROR: Expected build output {dist_dir} not found", file=sys.stderr)
        return 1

    # Wipe static_dir, then copy dist contents in
    if static_dir.exists():
        for item in static_dir.iterdir():
            if item.name == ".gitkeep":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    static_dir.mkdir(parents=True, exist_ok=True)

    for item in dist_dir.iterdir():
        dest = static_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    print(f"Built frontend bundle copied to {static_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run the build script**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python scripts/build_gui.py 2>&1 | tail -10`
Expected: `Built frontend bundle copied to /Users/nmurray/Developer/1d/engine_simulator/gui/static`

- [ ] **Step 4: Verify the static files are in place**

Run: `ls /Users/nmurray/Developer/1d/engine_simulator/gui/static/`
Expected: `index.html  assets/  .gitkeep` (or similar — at minimum `index.html` and an `assets/` directory).

- [ ] **Step 5: Manual smoke test the full server with frontend**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m engine_simulator.gui --no-browser &`
Wait 2 seconds, then run: `curl -s http://127.0.0.1:8765/ | head -5`
Expected: HTML output starting with `<!doctype html>` (the React app's index.html).
Then run: `curl -s http://127.0.0.1:8765/api/health`
Expected: `{"status":"ok"}`.
Then kill the server: `kill %1`.

- [ ] **Step 6: Save progress**

```bash
git add scripts/build_gui.py engine_simulator/gui/static/
git commit -m "feat(gui): build helper script + static bundle"
```

---

## Phase I: Frontend Infrastructure (state, websocket, REST client, types)

End of phase: the React app has working state management, WebSocket auto-reconnect, REST API wrappers, and TypeScript types matching the WS schema.

### Task I1: TypeScript event types matching the WebSocket schema

**Files:**
- Create: `gui-frontend/src/types/events.ts`

- [ ] **Step 1: Create the event types**

Create `gui-frontend/src/types/events.ts`:

```typescript
// TypeScript types matching the WebSocket message schema in
// engine_simulator/gui/sweep_manager.py and gui/snapshot.py.
// Keep these in sync with the Python side.

export interface RpmStartEvent {
  type: "rpm_start";
  rpm: number;
  rpm_index: number;
  n_cycles_target: number;
  ts: number;
}

export interface CycleDoneEvent {
  type: "cycle_done";
  rpm: number;
  cycle: number;
  delta: number;
  p_ivc: number[];
  step_count: number;
  elapsed: number;
  ts: number;
}

export interface ConvergedEvent {
  type: "converged";
  rpm: number;
  cycle: number;
  ts: number;
}

export interface RpmDoneEvent {
  type: "rpm_done";
  rpm: number;
  perf: PerfDict;
  elapsed: number;
  step_count: number;
  converged: boolean;
  ts: number;
  results_available: boolean;
}

export interface RpmErrorEvent {
  type: "rpm_error";
  rpm: number;
  error_type: string;
  error_msg: string;
  traceback: string;
  ts: number;
}

export interface SweepCompleteEvent {
  type: "sweep_complete";
  sweep_id: string;
  filename?: string;
  duration_seconds?: number;
  stopped?: boolean;
}

export interface SweepErrorEvent {
  type: "sweep_error";
  error_msg: string;
  traceback: string;
}

export interface PongMessage {
  type: "pong";
}

export interface SnapshotMessage {
  type: "snapshot";
  sweep: SweepSnapshot | null;
  available_sweeps: SweepSummary[];
}

export interface SweepSnapshot {
  status: "running" | "complete" | "error" | "stopped" | "idle";
  sweep_id: string;
  config_summary: {
    rpm_start: number;
    rpm_end: number;
    rpm_step: number;
    n_cycles: number;
    n_workers: number;
    config_name: string;
  };
  rpm_points: number[];
  started_at: string;
  elapsed_seconds: number;
  rpms: Record<string, RpmState>;
  results_by_rpm_summary: Record<string, { available: boolean }>;
}

export interface RpmState {
  status: "queued" | "running" | "done" | "error";
  rpm_index: number;
  current_cycle?: number;
  delta?: number;
  delta_history?: number[];
  p_ivc_history?: number[][];
  step_count?: number;
  elapsed?: number;
  perf?: PerfDict;
  converged?: boolean;
  converged_at_cycle?: number;
  error_type?: string;
  error_msg?: string;
  traceback?: string;
}

export interface PerfDict {
  rpm: number;
  indicated_power_hp: number;
  indicated_power_kW?: number;
  indicated_torque_Nm?: number;
  brake_power_hp: number;
  brake_power_kW?: number;
  brake_torque_Nm: number;
  wheel_power_hp?: number;
  wheel_power_kW?: number;
  wheel_torque_Nm?: number;
  drivetrain_efficiency?: number;
  imep_bar?: number;
  bmep_bar?: number;
  fmep_bar?: number;
  volumetric_efficiency_atm: number;
  volumetric_efficiency_plenum?: number;
  volumetric_efficiency?: number;
  intake_mass_per_cycle_g?: number;
  restrictor_choked?: boolean;
  restrictor_mdot?: number;
  plenum_pressure_bar?: number;
}

export interface SweepSummary {
  id: string;
  filename: string;
  started_at: string;
  duration_seconds: number;
  rpm_range: [number, number];
  n_rpm_points: number;
}

export type ServerMessage =
  | SnapshotMessage
  | RpmStartEvent
  | CycleDoneEvent
  | ConvergedEvent
  | RpmDoneEvent
  | RpmErrorEvent
  | SweepCompleteEvent
  | SweepErrorEvent
  | PongMessage;
```

- [ ] **Step 2: Verify TypeScript still compiles**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -10`
Expected: Build completes successfully.

- [ ] **Step 3: Save progress**

```bash
git add gui-frontend/src/types/events.ts
git commit -m "feat(gui-frontend): TypeScript types for WS messages"
```

---

### Task I2: REST API client + WebSocket client with auto-reconnect

**Files:**
- Create: `gui-frontend/src/api/client.ts`
- Create: `gui-frontend/src/api/websocket.ts`

- [ ] **Step 1: Create the REST API client**

Create `gui-frontend/src/api/client.ts`:

```typescript
import type { SweepSummary } from "../types/events";

const BASE = ""; // same origin (FastAPI serves both static + api)

export interface ConfigSummary {
  name: string;
  path: string;
  summary: string;
}

export interface StartSweepParams {
  rpm_start: number;
  rpm_end: number;
  rpm_step: number;
  n_cycles: number;
  n_workers: number;
  config_name: string;
}

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${url}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch {
      // body wasn't JSON
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => jsonFetch<{ status: string }>("/api/health"),

  listConfigs: () => jsonFetch<ConfigSummary[]>("/api/configs"),

  listSweeps: () => jsonFetch<SweepSummary[]>("/api/sweeps"),

  loadSweep: (id: string) =>
    jsonFetch<unknown>(`/api/sweeps/${encodeURIComponent(id)}`),

  startSweep: (params: StartSweepParams) =>
    jsonFetch<{ sweep_id: string; status: string }>("/api/sweep/start", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  stopSweep: () =>
    jsonFetch<{ status: string }>("/api/sweep/stop", { method: "POST" }),

  getCurrentResults: (rpm: number) =>
    jsonFetch<unknown>(`/api/sweeps/current/results/${rpm}`),
};
```

- [ ] **Step 2: Create the WebSocket client with auto-reconnect**

Create `gui-frontend/src/api/websocket.ts`:

```typescript
import type { ServerMessage } from "../types/events";

type Listener = (msg: ServerMessage) => void;

const RECONNECT_DELAYS_MS = [1000, 2000, 4000, 8000, 10000];

export class EventSocket {
  private ws: WebSocket | null = null;
  private listeners: Set<Listener> = new Set();
  private reconnectAttempt = 0;
  private heartbeatTimer: number | null = null;
  private closed = false;

  constructor(private url: string) {}

  connect() {
    this.closed = false;
    this._open();
  }

  private _open() {
    this.ws = new WebSocket(this.url);
    this.ws.onopen = () => {
      this.reconnectAttempt = 0;
      this._startHeartbeat();
    };
    this.ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as ServerMessage;
        this.listeners.forEach((l) => l(msg));
      } catch (e) {
        console.error("Failed to parse WS message", e);
      }
    };
    this.ws.onclose = () => {
      this._stopHeartbeat();
      if (!this.closed) {
        this._scheduleReconnect();
      }
    };
    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  private _scheduleReconnect() {
    const delay =
      RECONNECT_DELAYS_MS[
        Math.min(this.reconnectAttempt, RECONNECT_DELAYS_MS.length - 1)
      ];
    this.reconnectAttempt += 1;
    setTimeout(() => {
      if (!this.closed) this._open();
    }, delay);
  }

  private _startHeartbeat() {
    this.heartbeatTimer = window.setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);
  }

  private _stopHeartbeat() {
    if (this.heartbeatTimer !== null) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  addListener(l: Listener): () => void {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  }

  close() {
    this.closed = true;
    this._stopHeartbeat();
    this.ws?.close();
  }
}

export function makeEventSocket(): EventSocket {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${protocol}//${window.location.host}/ws/events`;
  return new EventSocket(url);
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -10`
Expected: Build succeeds.

- [ ] **Step 4: Save progress**

```bash
git add gui-frontend/src/api/
git commit -m "feat(gui-frontend): REST client + WS client with auto-reconnect"
```

---

### Task I3: Zustand sweep store + event reducer

**Files:**
- Create: `gui-frontend/src/state/sweepStore.ts`
- Create: `gui-frontend/src/state/eventReducer.ts`

- [ ] **Step 1: Create the Zustand store**

Create `gui-frontend/src/state/sweepStore.ts`:

```typescript
import { create } from "zustand";
import type { SweepSnapshot, SweepSummary, RpmState } from "../types/events";

export interface SweepStore {
  sweep: SweepSnapshot | null;
  availableSweeps: SweepSummary[];
  selectedRpm: number | null;
  // Per-RPM SimulationResults cache, keyed by `${sweep_id}:${rpm}`
  resultsCache: Record<string, unknown>;
  // WebSocket connection state
  connected: boolean;

  // Mutators
  setSnapshot: (sweep: SweepSnapshot | null, available: SweepSummary[]) => void;
  setSweep: (sweep: SweepSnapshot | null) => void;
  updateRpm: (rpm: number, partial: Partial<RpmState>) => void;
  setSelectedRpm: (rpm: number | null) => void;
  cacheResults: (sweepId: string, rpm: number, data: unknown) => void;
  setConnected: (c: boolean) => void;
}

export const useSweepStore = create<SweepStore>((set) => ({
  sweep: null,
  availableSweeps: [],
  selectedRpm: null,
  resultsCache: {},
  connected: false,

  setSnapshot: (sweep, available) =>
    set({ sweep, availableSweeps: available }),

  setSweep: (sweep) => set({ sweep }),

  updateRpm: (rpm, partial) =>
    set((state) => {
      if (!state.sweep) return state;
      const key = String(rpm);
      const existing = state.sweep.rpms[key] ?? state.sweep.rpms[String(Number(rpm))];
      if (!existing) return state;
      return {
        sweep: {
          ...state.sweep,
          rpms: {
            ...state.sweep.rpms,
            [key]: { ...existing, ...partial },
          },
        },
      };
    }),

  setSelectedRpm: (rpm) => set({ selectedRpm: rpm }),

  cacheResults: (sweepId, rpm, data) =>
    set((state) => ({
      resultsCache: {
        ...state.resultsCache,
        [`${sweepId}:${rpm}`]: data,
      },
    })),

  setConnected: (c) => set({ connected: c }),
}));
```

- [ ] **Step 2: Create the event reducer**

Create `gui-frontend/src/state/eventReducer.ts`:

```typescript
import type { ServerMessage, RpmState } from "../types/events";
import { useSweepStore } from "./sweepStore";

export function applyServerMessage(msg: ServerMessage): void {
  const store = useSweepStore.getState();

  switch (msg.type) {
    case "snapshot":
      store.setSnapshot(msg.sweep, msg.available_sweeps);
      break;

    case "rpm_start":
      store.updateRpm(msg.rpm, {
        status: "running",
        current_cycle: 0,
        rpm_index: msg.rpm_index,
        delta_history: [],
        p_ivc_history: [],
        step_count: 0,
        elapsed: 0,
      });
      break;

    case "cycle_done":
      const current = store.sweep?.rpms[String(msg.rpm)];
      const newDeltaHist = [
        ...(current?.delta_history ?? []),
        msg.delta,
      ];
      const newPivcHist = [
        ...(current?.p_ivc_history ?? []),
        msg.p_ivc,
      ];
      store.updateRpm(msg.rpm, {
        current_cycle: msg.cycle,
        delta: msg.delta,
        delta_history: newDeltaHist,
        p_ivc_history: newPivcHist,
        step_count: msg.step_count,
        elapsed: msg.elapsed,
      });
      break;

    case "converged":
      store.updateRpm(msg.rpm, { converged_at_cycle: msg.cycle });
      break;

    case "rpm_done":
      store.updateRpm(msg.rpm, {
        status: "done",
        perf: msg.perf,
        elapsed: msg.elapsed,
        step_count: msg.step_count,
        converged: msg.converged,
      });
      break;

    case "rpm_error":
      store.updateRpm(msg.rpm, {
        status: "error",
        error_type: msg.error_type,
        error_msg: msg.error_msg,
        traceback: msg.traceback,
      });
      break;

    case "sweep_complete":
      if (store.sweep) {
        store.setSweep({
          ...store.sweep,
          status: msg.stopped ? "stopped" : "complete",
        });
      }
      break;

    case "sweep_error":
      if (store.sweep) {
        store.setSweep({ ...store.sweep, status: "error" });
      }
      break;

    case "pong":
      // No-op
      break;
  }
}
```

- [ ] **Step 3: Build to verify TypeScript**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -10`
Expected: Build succeeds.

- [ ] **Step 4: Save progress**

```bash
git add gui-frontend/src/state/
git commit -m "feat(gui-frontend): Zustand store + event reducer"
```

---

## Phase J: Frontend Components (frontend-design INVOKED here)

End of phase: the React app renders the full Mission Control layout with live data flowing through the WebSocket. Each component task in this phase **invokes the `frontend-design` skill** with the spec's Section 5 (Visual Design Language) as the brief.

> **Sub-skill invocation pattern for every Phase J task:**
>
> Before writing the component, use the `Skill` tool with `skill: "frontend-design"`. When the agent loads, brief it with:
>
> > "Build the [ComponentName] component for the engine simulator GUI. The component file is `gui-frontend/src/components/[ComponentName].tsx`. The visual design language is in `docs/superpowers/specs/2026-04-08-engine-sim-gui-v1-design.md` Section 5 — read that section before designing. Color tokens, fonts, density rules, and chart conventions are all specified there. Reference points are Linear, Vercel, Cursor, Bloomberg Terminal — NOT Material Design or generic SaaS dashboards. Existing Tailwind tokens are in `gui-frontend/tailwind.config.js`. State is in `gui-frontend/src/state/sweepStore.ts`; types are in `gui-frontend/src/types/events.ts`."
>
> Then describe what the component must DO based on the task description below. Let the frontend-design agent decide the visual specifics within the brief's constraints.

### Task J1: App shell and TopBar

**Files:**
- Modify: `gui-frontend/src/App.tsx`
- Create: `gui-frontend/src/components/TopBar.tsx`

- [ ] **Step 1: Invoke frontend-design for TopBar**

Use the Skill tool with `skill: "frontend-design"` and the brief above. Tell it: "TopBar shows the app logo (text only, 'Engine Sim'), a primary 'Run Sweep' button (uses accent color), a 'Stop' button (only enabled when a sweep is running), a 'Load past sweep' dropdown trigger, and a status area on the right showing current sweep status, elapsed time, and ETA. ETA computed in TopBar from `useSweepStore`. Use icons from lucide-react: Play, Square, FolderOpen. Height: ~56px. Border-bottom in border-default. Status text uses font-mono."

- [ ] **Step 2: After frontend-design produces TopBar.tsx, update App.tsx**

Replace `gui-frontend/src/App.tsx`:

```typescript
import { useEffect } from "react";
import TopBar from "./components/TopBar";
import { makeEventSocket } from "./api/websocket";
import { applyServerMessage } from "./state/eventReducer";
import { useSweepStore } from "./state/sweepStore";

export default function App() {
  const setConnected = useSweepStore((s) => s.setConnected);

  useEffect(() => {
    const sock = makeEventSocket();
    const unsub = sock.addListener(applyServerMessage);
    sock.connect();
    setConnected(true);
    return () => {
      unsub();
      sock.close();
      setConnected(false);
    };
  }, [setConnected]);

  return (
    <div className="min-h-screen bg-bg text-text-primary font-ui flex flex-col">
      <TopBar />
      <main className="flex-1 flex items-center justify-center text-text-secondary">
        Phase J — components rendering
      </main>
    </div>
  );
}
```

- [ ] **Step 3: Build the frontend, then build the bundle and smoke test**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -10`
Expected: Build succeeds.

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python scripts/build_gui.py 2>&1 | tail -5`
Expected: Bundle copied.

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m engine_simulator.gui --no-browser &`
Wait 2 seconds, then open in browser: `http://127.0.0.1:8765/`
Expected: TopBar visible with the design from Section 5.
Then kill: `kill %1`.

- [ ] **Step 4: Save progress**

```bash
git add gui-frontend/src/App.tsx gui-frontend/src/components/TopBar.tsx engine_simulator/gui/static/
git commit -m "feat(gui-frontend): App shell and TopBar"
```

---

### Task J2: RunSweepDialog modal

**Files:**
- Create: `gui-frontend/src/components/RunSweepDialog.tsx`
- Modify: `gui-frontend/src/components/TopBar.tsx` (wire the Run button to open the dialog)

- [ ] **Step 1: Invoke frontend-design for RunSweepDialog**

Use Skill tool with `skill: "frontend-design"`. Brief: "RunSweepDialog is a modal triggered by the Run Sweep button in TopBar. Form fields: RPM start (number, default 6000), RPM end (number, default 13000), RPM step (number, default 1000), Cycles (number, default 12), Workers (number with slider 1-16, default 8), Config (dropdown populated from `api.listConfigs()`, default cbr600rr.json). Submit button: 'Start Sweep' in accent color. Cancel button. On submit, calls `api.startSweep(params)` and closes the modal. Modal uses surface-raised background, border-default, rounded-md. Backdrop is bg/80 with backdrop-blur-sm. Form labels in text-[10px] uppercase tracking-wider; inputs use the dark surface palette with border-default focused -> border-emphasis."

- [ ] **Step 2: Wire the dialog into TopBar**

After frontend-design produces RunSweepDialog.tsx, modify TopBar.tsx to manage the open/closed state and pass an `onRunClick` handler that opens the dialog. The TopBar already has the Run button — connect it to a `useState` for the modal open state, and conditionally render `<RunSweepDialog isOpen={...} onClose={...}/>`.

- [ ] **Step 3: Build and smoke test**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build && cd .. && .venv/bin/python scripts/build_gui.py`
Expected: Build succeeds.

Manual: start server, open browser, click "Run Sweep", verify modal appears with form fields. Close modal. Run a tiny sweep (RPM 8000-10000 step 1000, cycles 4, workers 2) — verify the sweep starts (you can check the terminal output).

- [ ] **Step 4: Save progress**

```bash
git add gui-frontend/src/components/RunSweepDialog.tsx gui-frontend/src/components/TopBar.tsx engine_simulator/gui/static/
git commit -m "feat(gui-frontend): RunSweepDialog modal"
```

---

### Task J3: SweepCurves (the headline charts)

**Files:**
- Create: `gui-frontend/src/components/SweepCurves.tsx`
- Create: `gui-frontend/src/components/charts/LineChart.tsx`
- Modify: `gui-frontend/src/App.tsx` (mount SweepCurves)

- [ ] **Step 1: Invoke frontend-design for SweepCurves + LineChart**

Use Skill tool with `skill: "frontend-design"`. Brief: "Build SweepCurves and a reusable LineChart wrapper. SweepCurves is a 6-chart grid (3 columns × 2 rows on wide viewports, 2×3 on narrow): Power vs RPM (3 series: indicated red, brake blue, wheel dashed-blue), Torque vs RPM (same 3 series), VE vs RPM (atm green, plenum dashed green, plus a horizontal reference line at 100%), IMEP/BMEP vs RPM (2 series), Plenum pressure vs RPM (1 series, with horizontal ref line at 1 bar), Restrictor mdot vs RPM (1 series, plus a red shaded band where restrictor_choked=true). LineChart wraps Recharts with the spec's chart conventions: no background grid lines, single 1.5px stroke per series, no fill, small filled circle markers (3px), axis text in mono font 10px text-secondary, no legend inside plot area (legends as a separate row above each chart in text-xs uppercase tracking-wider), tooltip uses surface-raised background with mono key:value rows. Data source: `useSweepStore((s) => s.sweep?.rpms)` — extract perf dicts from each RPM where status === 'done'. Click any data point → call `useSweepStore.setSelectedRpm(rpm)`. Selected RPM gets a vertical 1px accent-colored line across all charts."

- [ ] **Step 2: Mount SweepCurves in App.tsx**

Replace the `<main>` content in `App.tsx`:

```typescript
<main className="flex-1 overflow-auto p-3">
  <SweepCurves />
</main>
```

Add the import: `import SweepCurves from "./components/SweepCurves";`

- [ ] **Step 3: Build and smoke test**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build && cd .. && .venv/bin/python scripts/build_gui.py`

Manual: start server, open browser, run a tiny sweep (RPM 8000-10000 step 1000, cycles 4, workers 2). Verify SweepCurves appears with the empty grid, then data points appear as RPMs complete.

- [ ] **Step 4: Save progress**

```bash
git add gui-frontend/src/components/SweepCurves.tsx gui-frontend/src/components/charts/LineChart.tsx gui-frontend/src/App.tsx engine_simulator/gui/static/
git commit -m "feat(gui-frontend): SweepCurves with LineChart wrapper"
```

---

### Task J4: WorkersStrip and WorkerTile

**Files:**
- Create: `gui-frontend/src/components/WorkerTile.tsx`
- Create: `gui-frontend/src/components/WorkersStrip.tsx`
- Create: `gui-frontend/src/components/charts/Sparkline.tsx`
- Modify: `gui-frontend/src/App.tsx` (mount WorkersStrip)

- [ ] **Step 1: Invoke frontend-design for WorkerTile + WorkersStrip + Sparkline**

Use Skill tool with `skill: "frontend-design"`. Brief: "Build WorkerTile, WorkersStrip, and a tiny Sparkline component. A WorkerTile is a card showing one RPM's live state: large RPM number (font-mono text-2xl), tiny rpm_idx label, status icon + text (Loader2 spinning for running, Check for done, AlertTriangle for error, Clock for queued — all from lucide-react), current cycle/target ('cyc 5/12'), convergence delta as text + a small Sparkline of delta_history, elapsed seconds, and for done tiles a small perf summary (P_brk, T_brk, VE_atm). Status border colors per spec: queued=text-muted, running=accent (with a subtle glow), done=status-done, error=status-error. Tile padding p-2.5 to p-3. Border 1px. Tile is clickable — on click, calls setSelectedRpm(rpm). WorkersStrip is a horizontal grid (flex-wrap or grid auto-fit) of all RPMs in the current sweep. Hidden when no sweep is running. Sparkline is a tiny inline SVG line chart (~80px wide, 24px tall), single 1px stroke in accent color, no axes, no markers."

- [ ] **Step 2: Mount WorkersStrip in App.tsx**

Add `<WorkersStrip />` BELOW `<SweepCurves />` in App.tsx:

```typescript
<main className="flex-1 overflow-auto p-3 flex flex-col gap-3">
  <SweepCurves />
  <WorkersStrip />
</main>
```

Add the import: `import WorkersStrip from "./components/WorkersStrip";`

- [ ] **Step 3: Build and smoke test**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build && cd .. && .venv/bin/python scripts/build_gui.py`

Manual: start server, open browser, run a tiny sweep. Verify WorkersStrip appears with one tile per RPM, tiles update live with cycle counter and delta sparkline, completed tiles flip to done state with perf summary.

- [ ] **Step 4: Save progress**

```bash
git add gui-frontend/src/components/WorkerTile.tsx gui-frontend/src/components/WorkersStrip.tsx gui-frontend/src/components/charts/Sparkline.tsx gui-frontend/src/App.tsx engine_simulator/gui/static/
git commit -m "feat(gui-frontend): WorkersStrip with WorkerTile and Sparkline"
```

---

### Task J5: RpmDetail panel skeleton + Cylinders tab + P-V tab

**Files:**
- Create: `gui-frontend/src/components/RpmDetail.tsx`
- Create: `gui-frontend/src/components/CylinderTraces.tsx`
- Create: `gui-frontend/src/components/PvDiagrams.tsx`
- Modify: `gui-frontend/src/App.tsx`

- [ ] **Step 1: Invoke frontend-design for RpmDetail + Cylinders + PvDiagrams**

Use Skill tool with `skill: "frontend-design"`. Brief: "Build the RpmDetail panel with tabs and the Cylinders + P-V tab content. RpmDetail header shows the selected RPM (large mono number with a dropdown to switch RPMs) and tabs across the top: Cylinders, P-V, Pipes, Plenum, Restrictor, Cycle Convergence (only Cylinders + P-V are implemented in this task; the other tabs render 'Not implemented yet' for now). When an RPM is selected, RpmDetail fetches `/api/sweeps/current/results/{rpm}` and caches in the store via `cacheResults(sweepId, rpm, data)`. While loading, show a placeholder. Once loaded, render the active tab's content. Cylinders tab: a row of 4 small cylinder pressure traces (LineChart wrapper, each ~200px tall), pressure (bar) vs crank angle (deg), one per cylinder, plus a large overlay chart below showing all 4 on the same axes. PvDiagrams tab: 4 P-V indicator diagrams (1 large for the selected cylinder, 3 small thumbnails along the side), with a log-scale toggle. Selected cylinder defaults to 0 (the first); add tiny number buttons 1-4 to switch."

- [ ] **Step 2: Mount RpmDetail in App.tsx**

Add `<RpmDetail />` BELOW `<WorkersStrip />` in App.tsx:

```typescript
<main className="flex-1 overflow-auto p-3 flex flex-col gap-3">
  <SweepCurves />
  <WorkersStrip />
  <RpmDetail />
</main>
```

Add the import.

- [ ] **Step 3: Build and smoke test**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build && cd .. && .venv/bin/python scripts/build_gui.py`

Manual: run a small sweep, click a completed RPM tile in WorkersStrip, verify RpmDetail loads with the Cylinders tab showing 4 cylinder pressure traces. Click the P-V tab, verify P-V diagrams render.

- [ ] **Step 4: Save progress**

```bash
git add gui-frontend/src/components/RpmDetail.tsx gui-frontend/src/components/CylinderTraces.tsx gui-frontend/src/components/PvDiagrams.tsx gui-frontend/src/App.tsx engine_simulator/gui/static/
git commit -m "feat(gui-frontend): RpmDetail panel + Cylinders and P-V tabs"
```

---

### Task J6: RpmDetail Pipes / Plenum / Restrictor / CycleConvergence tabs

**Files:**
- Create: `gui-frontend/src/components/PipeTraces.tsx`
- Create: `gui-frontend/src/components/PlenumPanel.tsx`
- Create: `gui-frontend/src/components/RestrictorPanel.tsx`
- Create: `gui-frontend/src/components/CycleConvergencePanel.tsx`
- Modify: `gui-frontend/src/components/RpmDetail.tsx` (wire the new tabs)

- [ ] **Step 1: Invoke frontend-design for the four tab content components**

Use Skill tool with `skill: "frontend-design"`. Brief: "Build PipeTraces, PlenumPanel, RestrictorPanel, and CycleConvergencePanel. PipeTraces: a grid of pipe pressure traces at midpoint (4 intake runners + 4 exhaust primaries + 2 exhaust secondaries + 1 collector = 11 panels). Each panel shows pressure (bar) and velocity (m/s) on twin Y axes (or stacked). Hovering syncs a vertical crank-angle line across all panels (use a shared hover state via prop or context). PlenumPanel: two stacked LineChart wrappers, plenum pressure (bar) vs crank angle and plenum temperature (K) vs crank angle. Reference horizontal line at atmospheric pressure (1.013 bar) on the pressure chart. RestrictorPanel: mass flow vs crank angle line chart, with a red shaded band wherever restrictor_choked is true. Below the chart: scalar readouts in a 2x2 grid (Total intake mass per cycle in g, Choked time fraction in %, Peak mdot in g/s, Mean mdot in g/s) using mono font. CycleConvergencePanel: a table showing cycle-by-cycle convergence delta + per-cylinder p_at_IVC values from the rpm state's delta_history and p_ivc_history (already in the sweep store, no fetch needed). Below the table, a small line chart of delta vs cycle number to visualize convergence. Use the spec's table styling: h-7 row height, font-mono for numeric values, border-default hairlines."

- [ ] **Step 2: Wire the new tab content into RpmDetail**

In RpmDetail.tsx, replace the placeholder "Not implemented yet" branches in the tab switch with the actual component imports and renders.

- [ ] **Step 3: Build and smoke test**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build && cd .. && .venv/bin/python scripts/build_gui.py`

Manual: run a sweep, click a completed RPM, click each of the four new tabs, verify they render data.

- [ ] **Step 4: Save progress**

```bash
git add gui-frontend/src/components/PipeTraces.tsx gui-frontend/src/components/PlenumPanel.tsx gui-frontend/src/components/RestrictorPanel.tsx gui-frontend/src/components/CycleConvergencePanel.tsx gui-frontend/src/components/RpmDetail.tsx engine_simulator/gui/static/
git commit -m "feat(gui-frontend): RpmDetail Pipes/Plenum/Restrictor/Convergence tabs"
```

---

### Task J7: SweepListSidebar (load past sweeps)

**Files:**
- Create: `gui-frontend/src/components/SweepListSidebar.tsx`
- Modify: `gui-frontend/src/App.tsx`

- [ ] **Step 1: Invoke frontend-design for SweepListSidebar**

Use Skill tool with `skill: "frontend-design"`. Brief: "Build SweepListSidebar — a collapsible right-edge sidebar listing past sweeps from `useSweepStore((s) => s.availableSweeps)`. Each entry shows: timestamp (font-mono text-xs), RPM range (e.g. '6000-13000'), duration ('5m 27s'), worker count. Newest at the top. Clicking an entry → confirmation dialog ('Switch to this sweep? Current view will be replaced.') → on confirm, calls `api.loadSweep(id)`. On success, the snapshot WS message will populate the store. Sidebar collapses to a thin 32px rail when not in use (animated via Tailwind transition-all duration-150). Collapse toggle is a chevron button (lucide ChevronRight / ChevronLeft) at the top of the rail. Sidebar background: surface, border-l in border-default."

- [ ] **Step 2: Mount the sidebar in App.tsx**

Wrap the existing layout in a flex container so the sidebar can sit to the right:

```typescript
return (
  <div className="min-h-screen bg-bg text-text-primary font-ui flex flex-col">
    <TopBar />
    <div className="flex-1 flex overflow-hidden">
      <main className="flex-1 overflow-auto p-3 flex flex-col gap-3">
        <SweepCurves />
        <WorkersStrip />
        <RpmDetail />
      </main>
      <SweepListSidebar />
    </div>
  </div>
);
```

Add the import.

- [ ] **Step 3: Build and smoke test**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build && cd .. && .venv/bin/python scripts/build_gui.py`

Manual: run a sweep, wait for it to finish (so a file is auto-saved). Open the sidebar (collapse rail). Verify the sweep appears. Click it, confirm, verify the sweep loads in the main view.

- [ ] **Step 4: Save progress**

```bash
git add gui-frontend/src/components/SweepListSidebar.tsx gui-frontend/src/App.tsx engine_simulator/gui/static/
git commit -m "feat(gui-frontend): SweepListSidebar for loading past sweeps"
```

---

## Phase K: End-to-end manual smoke test

End of phase: the 12 manual smoke test steps from spec Section 8 Layer 4 all pass. The GUI is ready for v1 release.

### Task K1: Run the full test suite + manual smoke test

**Files:**
- (None — verification only)

- [ ] **Step 1: Run the full Python test suite**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/ --tb=no -q 2>&1 | tail -15`
Expected: All tests pass (existing 89 from previous work + the new GUI tests).

- [ ] **Step 2: Run the GUI sweep equivalence test specifically**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pytest tests/test_gui_sweep_equivalence.py -v 2>&1 | tail -10`
Expected: Bit-identical results between GUI and CLI paths.

- [ ] **Step 3: Build the production bundle**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build && cd .. && .venv/bin/python scripts/build_gui.py`
Expected: Built bundle copied to `engine_simulator/gui/static/`.

- [ ] **Step 4: Manual smoke test (12 steps from spec Section 8 Layer 4)**

Follow the 12-step manual smoke test from the spec verbatim. Each step has expected behavior listed. If any step fails, that's a v1 bug to investigate before merging.

Briefly:
1. Start server → browser auto-opens.
2. App loads with idle state.
3. Open Run Sweep dialog, fill form, start.
4. Watch live: workers strip, cycles updating, sweep curves filling in.
5. Click an RPM tile, navigate the detail tabs.
6. Verify auto-save: `ls -la sweeps/`, inspect with `jq`.
7. Reload browser tab, verify state preserved.
8. Click Load past sweep, verify it loads.
9. Run another sweep, verify both files exist on disk.
10. Click Stop mid-sweep, verify cleanup.
11. Trigger an error (invalid config), verify error tile.
12. Close browser, verify server shuts down after ~10s.

- [ ] **Step 5: Save progress**

```bash
git add -A
git commit -m "feat(gui): GUI v1 implementation complete"
```

---

## Spec Coverage Map

For each section of the spec, the corresponding implementation task:

| Spec Section | Implementation Task(s) |
|---|---|
| Section 1: Architecture & Process Model — FastAPI + browser, single command launch | A1, A2 |
| Section 2: Module & File Layout — `engine_simulator/gui/`, `gui-frontend/`, `sweeps/`, tests | A1 (skeleton), all phases |
| Section 3: WebSocket Protocol & Data Flow — message schemas | C3 (event_to_json), G2 (WebSocket route), I1 (TS types) |
| Section 3: REST endpoints — `/api/health`, `/configs`, `/sweeps`, `/sweep/start`, etc. | A2, F1, F2 |
| Section 4: Mission Control Layout — TopBar, SweepCurves, WorkersStrip, RpmDetail, Sidebar | J1-J7 |
| Section 5: Visual Design Language — colors, fonts, density rules, charts, icons, animations | H2 (Tailwind tokens), J1-J7 (frontend-design invocations brief against this section) |
| Section 6: Sweep Persistence — file format, atomic save, schema versioning | E1, E2 |
| Section 7: Solver Process Integration — GUIEventConsumer, SweepManager, threading model | B1, C1, C2, C3 |
| Section 7: Bit-identity guarantee | D1 (Layer 1 keystone) |
| Section 8: Testing — Layers 1-4 | D1 (L1), E1+E2 (L2), B1/C2/C3/E1/E2/F1/F2/G1/G2 (L3), K1 (L4 manual) |
| Decision log items 1-12 | All embedded in the relevant phases |
| Implementation sequencing 1-17 | Phases A through K mirror this order |

## Decision Recap (from spec, repeated here so the engineer doesn't have to flip)

1. **Two-spec split: v1 = Live + Report, v2 = Config Editor.** This plan covers v1 only.
2. **Local laptop, FastAPI + React + Tailwind on localhost:8765.**
3. **One-command launch.** `python -m engine_simulator.gui` starts server + opens browser.
4. **Mission Control layout.** Sweep curves on top, workers strip in middle, RpmDetail at bottom, sidebar for past sweeps.
5. **Auto-save every sweep to `sweeps/`** as a self-contained JSON file with `engine_config` snapshot.
6. **`GUIEventConsumer` is the only integration seam** with the existing solver. Zero changes to solver code.
7. **Sweep runner in a dedicated thread, asyncio loop in main thread** with `call_soon_threadsafe` bridging.
8. **Layer 1 equivalence test for the GUI path** — guarantees bit-identical results vs CLI.
9. **Visual identity pinned in spec Section 5, executed by `frontend-design` skill in Phase J** — prevents AI-slop aesthetics.
10. **Charts: hairline strokes, no grid, mono axes, no legend in plot area** — distinctive instrument look.
11. **Partial sweeps NOT auto-saved on stop** — keeps file format simple in v1.
12. **Schema version 1** — load-time guard for future format changes.
