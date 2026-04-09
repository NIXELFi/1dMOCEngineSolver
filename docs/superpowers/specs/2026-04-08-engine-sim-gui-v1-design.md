# Engine Simulator GUI v1 — Design (Live + Report)

**Date:** 2026-04-08
**Author:** brainstormed with Claude
**Status:** Approved (pending implementation plan)

## Motivation

The 1D engine simulator is currently a CLI tool. Today's parallelization work added a structured progress event stream (`EventConsumer` protocol in `engine_simulator/simulation/parallel_sweep.py`) explicitly so a future GUI could consume it. This spec defines that GUI's first version.

The user's goal is "real-time view of everything during a sweep, plus a polished report when it's finished." This spec covers both — they're the same UI showing different data sources (live event stream vs. completed `SimulationResults`).

## Scope decomposition

The full GUI vision has three independent UI surfaces:

1. **Live monitor** — watch a sweep run, per-RPM panels, sweep curves filling in
2. **Polished report** — browse completed sweeps with the same panels, frozen
3. **Configuration editor** — form widgets bound to `EngineConfig`, "Run" button

Surfaces 1 and 2 share the same components (same plots, same layout, just different data sources) so they belong in one spec. Surface 3 is a separate UI entirely (forms, validation, save/load) and gets its own spec.

**This spec covers v1: surfaces 1 and 2 only.** The configuration editor is v2 and will be brainstormed separately after v1 lands.

## Hard constraints

1. **Numerical results unchanged.** A sweep run via the GUI must produce bit-for-bit identical perf dicts compared to a CLI sweep with the same parameters. The GUI integrates with the solver via the `EventConsumer` protocol from today's parallelization work; that protocol is read-only by design. The Layer 1 equivalence test from today's work must continue to pass without modification, and a new Layer 1 test is added that drives the GUI's `SweepManager` and asserts bit-identity vs. the CLI path.
2. **Solver code is not touched.** No changes to `parallel_sweep.py`, `orchestrator.py`, `gas_dynamics/`, `engine/`, `boundaries/`, `simulation/plenum.py|convergence.py|engine_cycle.py`, or `postprocessing/`. The GUI is purely additive — a new top-level package `engine_simulator/gui/` and a sibling `gui-frontend/` directory.
3. **CLI is not touched.** `python -m engine_simulator.main sweep --workers 8` continues to work exactly as it does today, with `CLIEventConsumer`. The GUI is a separate entry point.
4. **One-command launch.** `python -m engine_simulator.gui` starts the server, opens a browser, and you're in the app. No manual coordination of multiple processes.
5. **Polished aesthetic, not generic AI dashboard.** The visual identity is pinned down in the "Visual Design Language" section of this spec and executed by the `frontend-design` skill during implementation.

## Out of scope

- Configuration editor (form widgets, save/load configs from the UI). v2.
- Multi-machine / hosted deployment. v3+.
- Comparing two sweeps side-by-side. v3+.
- Visual regression / screenshot tests.
- Cross-browser compatibility beyond the user's default macOS browser.
- Real-time editing of a sweep mid-flight.
- Authentication or multi-user support.

---

## Section 1 — Architecture & Process Model

**Two processes in one launch:** a Python FastAPI server + the user's default browser navigating to it.

```
                ┌──────────────────────────────────────────┐
                │       python -m engine_simulator.gui      │
                └──────────────────┬────────────────────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              │                                          │
              ▼                                          ▼
   ┌──────────────────────┐                ┌────────────────────────┐
   │  FastAPI server      │                │  Default web browser   │
   │  on localhost:8765   │                │  navigates to          │
   │                      │                │  http://localhost:8765 │
   │  • REST endpoints    │◄───WebSocket──►│                        │
   │  • WebSocket /events │                │  React + Tailwind app  │
   │  • Static React bundle                │  (built bundle served  │
   │  • Owns ParallelSweepRunner            │   by FastAPI)          │
   └──────────┬───────────┘                └────────────────────────┘
              │
              │ spawns (via existing ParallelSweepRunner)
              ▼
   ┌────────────────────────┐
   │  Worker processes      │
   │  (existing             │
   │   ParallelSweepRunner) │
   └────────────────────────┘
```

**Process flow when the user runs `python -m engine_simulator.gui`:**

1. Python starts the FastAPI server bound to `127.0.0.1` on a configurable port (default `8765`)
2. The server opens the default browser at `http://localhost:8765/` (via `webbrowser.open()`)
3. The browser loads the static React bundle (pre-built, served from `engine_simulator/gui/static/`)
4. The React app immediately connects a WebSocket to `/ws/events`
5. User clicks "Run Sweep" → React POSTs `/api/sweep/start` → server kicks off `ParallelSweepRunner` in a background asyncio task → events stream into a queue → the queue gets pumped onto the WebSocket → React renders updates live
6. When the sweep finishes, the server auto-saves the JSON file to `sweeps/` and broadcasts a `sweep_complete` WebSocket message

**Key properties:**

- **One process model, not Electron.** FastAPI + browser, no native shell. Tiny startup overhead, no packaging concerns.
- **Solver runs as worker processes.** The existing `ParallelSweepRunner` from today's work, unchanged. The FastAPI server is just the conductor — it owns the runner, drains its event queue, and forwards events to connected WebSocket clients.
- **`GUIEventConsumer` is the integration seam.** A new class implementing the existing `EventConsumer` protocol from `parallel_sweep.py`. Its `handle()` method puts events on an asyncio queue that the WebSocket pump drains. **This is the entire integration point** between the GUI and the solver.
- **Reload-safe.** If the user closes and reopens the browser tab during a sweep, the new tab reconnects to the WebSocket and immediately receives a "current state snapshot" message so it can render the in-progress sweep correctly. No work is lost.
- **Shutdown:** when the user closes the browser tab, the server keeps running for ~10 seconds in case they reload, then shuts down. `Ctrl-C` in the terminal also kills it. If a sweep is in progress when the server is killed, the worker processes are killed too.

---

## Section 2 — Module & File Layout

### New top-level package: `engine_simulator/gui/`

```
engine_simulator/
├── gui/
│   ├── __init__.py
│   ├── __main__.py              ← `python -m engine_simulator.gui` entry point
│   ├── server.py                ← FastAPI app + ASGI lifespan + browser launch
│   ├── routes_api.py            ← REST endpoints
│   ├── routes_ws.py             ← WebSocket /ws/events endpoint
│   ├── sweep_manager.py         ← Owns ParallelSweepRunner lifecycle, event queue,
│   │                              and the in-memory current sweep state.
│   │                              Single source of truth for what's running.
│   ├── gui_event_consumer.py    ← EventConsumer impl that puts events on an
│   │                              asyncio queue for the WebSocket pump
│   ├── persistence.py           ← Save/load sweep .json files in sweeps/
│   ├── snapshot.py              ← Builds "current sweep state" snapshots for
│   │                              reconnecting clients
│   └── static/                  ← Pre-built React bundle (from gui-frontend/dist/)
│       ├── index.html
│       ├── assets/
│       │   ├── index-[hash].js
│       │   └── index-[hash].css
│       └── ...
├── simulation/                  ← UNCHANGED by this spec
│   ├── orchestrator.py
│   └── parallel_sweep.py
└── ... (rest unchanged)

gui-frontend/                    ← React+Tailwind source (NOT shipped, only built)
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── tsconfig.json
├── index.html
├── src/
│   ├── main.tsx
│   ├── App.tsx                  ← Top-level layout (Mission Control)
│   ├── api/
│   │   ├── client.ts            ← REST client
│   │   └── websocket.ts         ← WebSocket connection + auto-reconnect
│   ├── state/
│   │   ├── sweepStore.ts        ← Zustand store: current sweep state
│   │   └── eventReducer.ts      ← Translates incoming events into state updates
│   ├── components/
│   │   ├── TopBar.tsx
│   │   ├── RunSweepDialog.tsx
│   │   ├── SweepCurves.tsx
│   │   ├── WorkerTile.tsx
│   │   ├── WorkersStrip.tsx
│   │   ├── RpmDetail.tsx
│   │   ├── CylinderTraces.tsx
│   │   ├── PipeTraces.tsx
│   │   ├── PlenumPanel.tsx
│   │   ├── RestrictorPanel.tsx
│   │   ├── SweepListSidebar.tsx
│   │   └── charts/
│   │       ├── LineChart.tsx
│   │       ├── Sparkline.tsx
│   │       └── Gauge.tsx
│   └── types/
│       └── events.ts
├── public/
└── dist/                        ← Build output, copied to engine_simulator/gui/static/

sweeps/                          ← Created on first sweep run; auto-saved JSON files
└── 2026-04-08T18-23-04_6000-13000_step1000_12cyc.json

scripts/
└── build_gui.py                 ← Build helper: runs vite build + copies dist into static/

tests/
├── test_gui_sweep_equivalence.py    ← Layer 1: GUI vs CLI bit-identity
├── test_gui_persistence.py          ← Layer 2: save/load round-trip
├── test_gui_event_consumer.py       ← Layer 3: event consumer plumbing
├── test_gui_sweep_manager.py        ← Layer 3: SweepManager orchestration
├── test_gui_routes_api.py           ← Layer 3: REST endpoint integration
├── test_gui_routes_ws.py            ← Layer 3: WebSocket protocol
└── test_gui_snapshot.py             ← Layer 3: snapshot serialization
```

### Build flow

1. `cd gui-frontend && npm install` (one-time developer setup)
2. `cd gui-frontend && npm run build` produces `gui-frontend/dist/`
3. `python scripts/build_gui.py` copies `dist/*` into `engine_simulator/gui/static/`
4. The Python package ships with the pre-built static bundle inside it. End users don't need Node — just `python -m engine_simulator.gui`.

### Why this layout

- **`gui/` is fully isolated.** Nothing in `engine_simulator/simulation/`, `gas_dynamics/`, `engine/`, `boundaries/`, or `postprocessing/` is imported by `gui/` except via the `EventConsumer` protocol from `parallel_sweep.py`.
- **`gui-frontend/` is a separate top-level directory.** Keeps the JS/TS toolchain (`node_modules`, vite, tailwind) out of the Python package's `MANIFEST`. Build output is the only thing that crosses the boundary.
- **Backend modules split by concern.** `routes_api.py` is REST, `routes_ws.py` is WebSocket, `sweep_manager.py` owns lifecycle, `persistence.py` is file I/O, `snapshot.py` builds replayable state. Each is independently testable.
- **Frontend components are small and focused.** Each `.tsx` file is roughly 50-150 lines of TSX. JSX + logic + types stack up fast in React; small files keep them reasonable.

### Files NOT touched

- `engine_simulator/simulation/orchestrator.py`, `parallel_sweep.py`
- `engine_simulator/gas_dynamics/*`, `engine/*`, `boundaries/*`
- `engine_simulator/simulation/plenum.py`, `convergence.py`, `engine_cycle.py`
- `engine_simulator/postprocessing/*`
- `engine_simulator/main.py` (CLI)
- `_run_sweep.py`, `_run_sweep_fast.py` (custom drivers)

---

## Section 3 — WebSocket Protocol & Data Flow

### Server → Client message types

All messages are JSON with a `type` field. Payloads mirror the Python event dataclasses from `parallel_sweep.py`.

```jsonc
// 1. State snapshot — sent immediately on every new WebSocket connection.
//    Lets a freshly opened tab render the current sweep without missing events.
{
  "type": "snapshot",
  "sweep": null | {
    "status": "idle" | "running" | "complete" | "error" | "stopped",
    "sweep_id": "2026-04-08T18-23-04_6000-13000_step1000_12cyc",
    "config_summary": {
      "rpm_start": 6000, "rpm_end": 13000, "rpm_step": 1000,
      "n_cycles": 12, "n_workers": 8, "config_name": "cbr600rr.json"
    },
    "rpm_points": [6000, 7000, 8000, 9000, 10000, 11000, 12000, 13000],
    "started_at": "2026-04-08T18:23:04Z",
    "elapsed_seconds": 73.2,
    "rpms": {
      "6000": {
        "status": "running",
        "rpm_index": 0,
        "current_cycle": 4,
        "delta": 0.0823,
        "delta_history": [0.0823, 0.0341, 0.0118, 0.0042],
        "p_ivc_history": [[95000, 96000, 95500, 96100], ...],
        "step_count": 1241,
        "elapsed": 12.4
      },
      "7000": { "status": "queued", "rpm_index": 1 },
      "8000": {
        "status": "done",
        "rpm_index": 2,
        "perf": { /* full perf dict */ },
        "elapsed": 11.2,
        "step_count": 4523,
        "converged": true
      }
    },
    "results_by_rpm_summary": {
      "8000": { "available": true }
    }
  },
  "available_sweeps": [
    {
      "id": "2026-04-08T17-12-33_6000-13000_step1000_12cyc",
      "filename": "2026-04-08T17-12-33_6000-13000_step1000_12cyc.json",
      "started_at": "2026-04-08T17:12:33Z",
      "duration_seconds": 327.7,
      "rpm_range": [6000, 13000],
      "n_rpm_points": 8
    }
  ]
}

// 2. RPM start
{ "type": "rpm_start", "rpm": 8000, "rpm_index": 2,
  "n_cycles_target": 12, "ts": 1234.5 }

// 3. Cycle done
{ "type": "cycle_done", "rpm": 8000, "cycle": 1,
  "delta": 0.0823, "p_ivc": [95000, 96000, 95500, 96100],
  "step_count": 1241, "elapsed": 12.4, "ts": 1245.7 }

// 4. Converged
{ "type": "converged", "rpm": 8000, "cycle": 4, "ts": 1278.3 }

// 5. RPM done — full perf dict + flag indicating SimulationResults are now fetchable
{ "type": "rpm_done", "rpm": 8000,
  "perf": { "indicated_power_hp": 89.9, "brake_power_hp": 72.2, /* ... */ },
  "elapsed": 66.8, "step_count": 6507, "converged": true, "ts": 1311.3,
  "results_available": true }

// 6. RPM error
{ "type": "rpm_error", "rpm": 9000, "error_type": "ValueError",
  "error_msg": "...", "traceback": "...", "ts": 1320.0 }

// 7. Sweep complete (after all RPMs done AND auto-save finished)
{ "type": "sweep_complete", "sweep_id": "...", "filename": "...json",
  "duration_seconds": 327.7 }

// 8. Sweep error (fatal error in the sweep itself)
{ "type": "sweep_error", "error_msg": "...", "traceback": "..." }

// 9. Pong (heartbeat response)
{ "type": "pong" }
```

### Client → Server messages

The client sends very little over the WebSocket — most actions go through REST. The only WS message is a heartbeat:

```jsonc
{ "type": "ping" }    // every 30s, server responds with {"type":"pong"}
```

### REST endpoints

| Method | Path | Body | Response | Purpose |
|---|---|---|---|---|
| `GET` | `/api/health` | — | `{status:"ok"}` | Server liveness check |
| `GET` | `/api/configs` | — | `[{name, path, summary},...]` | List `.json` configs in `engine_simulator/config/` |
| `GET` | `/api/configs/{name}` | — | full `EngineConfig` JSON | Inspect a config (read-only in v1) |
| `POST` | `/api/sweep/start` | `{rpm_start, rpm_end, rpm_step, n_cycles, n_workers, config_name}` | `{sweep_id, status:"running"}` | Kick off a sweep. Returns immediately; events arrive via WS. Returns 409 if a sweep is already running. |
| `POST` | `/api/sweep/stop` | — | `{status:"stopped"}` | Cancel the running sweep (kills worker pool). Idempotent. |
| `GET` | `/api/sweeps` | — | `[{id, filename, started_at, duration_seconds, rpm_range, n_rpm_points}, ...]` | List saved sweeps in `sweeps/` |
| `GET` | `/api/sweeps/{id}` | — | full sweep JSON | Load a past sweep into memory and broadcast a snapshot |
| `GET` | `/api/sweeps/current/results/{rpm}` | — | per-RPM `SimulationResults` JSON | Lazily fetch heavy time-series data for one RPM of the live sweep |
| `GET` | `/api/sweeps/{id}/results/{rpm}` | — | per-RPM `SimulationResults` JSON | Lazily fetch heavy data for one RPM of a past sweep |

### Why heavy data goes through REST, not WebSocket

- A `SimulationResults` for one RPM is potentially hundreds of KB (theta_history, dt_history, 4 cylinder probe arrays, ~11 pipe probe arrays, plenum, restrictor)
- Pushing this through the WebSocket for every completed RPM would saturate the wire and stall the live event stream
- Instead: when the user clicks an RPM in the UI to see its detail, the React app fetches `/api/sweeps/current/results/{rpm}` once, caches it, and renders the detail tabs from that cached payload
- For past sweeps, the entire file is loaded in one shot via `/api/sweeps/{id}` (the file is already on disk)

### Reconnect / resync flow

1. Tab opens (or reopens) → WebSocket connects to `/ws/events`
2. Server immediately sends a `snapshot` message with the entire current sweep state
3. React app uses the snapshot to fully reconstruct its UI state
4. From there, normal incremental events stream in
5. If the WebSocket drops mid-sweep, React auto-reconnects with exponential backoff (1s, 2s, 4s, 8s, capped at 10s) and gets a fresh snapshot on reconnect

The server is the single source of truth. The browser tab is fully recoverable.

---

## Section 4 — Mission Control Layout

The visual heart of v1. The window is divided into four regions stacked top-to-bottom, plus a collapsible sidebar on the right edge.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ TopBar: [logo] [Run Sweep ▾] [⏹ Stop] [Load past sweep ▾] | sweep status    │
│                                                            elapsed  ETA      │
├──────────────────────────────────────────────────────────────────────────────┤
│  ┌────────────── SweepCurves (always visible) ──────────────────────────┐   │
│  │  Power vs RPM      [Indicated · Brake · Wheel]                       │   │
│  │  Torque vs RPM     [Indicated · Brake · Wheel]                       │   │
│  │  VE vs RPM         [Atm-ref · Plenum-ref]                            │   │
│  │  IMEP/BMEP vs RPM                                                    │   │
│  │  Plenum p_max vs RPM   |   Restrictor mdot vs RPM   |  Choking band  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────────────────┤
│  ┌─ WorkersStrip (collapses to 0px when no sweep is running) ───────────┐   │
│  │ ┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐         │   │
│  │ │ 6000   ││ 7000   ││ 8000   ││ 9000   ││ 10000  ││ 11000  │  ...    │   │
│  │ │ ▶ run  ││ ▶ run  ││ ▶ run  ││ ▶ run  ││ ✓ done ││ ⏳ q   │         │   │
│  │ │ cyc 4  ││ cyc 6  ││ cyc 5  ││ cyc 3  ││P=72.2hp││        │         │   │
│  │ │ δ.0341 ││ δ.0204 ││ δ.0312 ││ δ.0712 ││T=64Nm  ││        │         │   │
│  │ │ ╱╲╱╲╱╲ ││ ╱╲╱╲╱╲ ││ ╱╲╱╲╱╲ ││ ╱╲╱╲   ││VE 107% ││        │         │   │
│  │ │ 12.4s  ││ 9.1s   ││ 11.2s  ││ 5.3s   ││66.8s   ││        │         │   │
│  │ └────────┘└────────┘└────────┘└────────┘└────────┘└────────┘         │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────────────────┤
│  ┌─ RpmDetail (selected RPM) ─────────────────────────────────────────────┐ │
│  │  Selected: 8000 RPM ▾   Tabs: [Cylinders][P-V][Pipes][Plenum][Restr.]  │ │
│  │ ┌──────────────────────────────────────────────────────────────────┐   │ │
│  │ │   (large detail charts for the active tab)                       │   │ │
│  │ └──────────────────────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────┤
│ Sidebar (collapsible right edge): SweepListSidebar — past sweeps, click to load│
└──────────────────────────────────────────────────────────────────────────────┘
```

### TopBar

- **Run Sweep button** → opens a `RunSweepDialog` modal with form fields:
  - RPM start, RPM end, RPM step
  - Cycles (default 12)
  - Workers (default `min(cpu_count, n_rpm_points)`, slider 1..16)
  - Config dropdown (lists `engine_simulator/config/*.json`)
  - "Start" button → POSTs `/api/sweep/start`
- **Stop button** → POSTs `/api/sweep/stop`. Disabled when no sweep is running. Confirms before killing.
- **Load past sweep** → opens a popover with a dropdown of saved sweeps. Clicking one loads it into the entire view.
- **Status area** (right side):
  - During run: `Running · 4/8 RPMs done · elapsed 1m 12s · ETA ~3m 40s`
  - When idle: `Idle · last sweep: 2026-04-08 17:12 (5m 27s)`
  - On error: `Error: <message>` in the accent red
- **ETA calculation**: as RPMs complete, average their elapsed time and multiply by the number of RPMs left. Refresh on every RPM done.

### SweepCurves (top region, ~40% viewport, always visible)

A 2x3 grid (or 3x2 depending on viewport):

| Chart | Data | Notes |
|---|---|---|
| Power vs RPM | `indicated_power_hp`, `brake_power_hp`, `wheel_power_hp` | 3 line series, palette matches the existing matplotlib `r-o`/`b-s`/`b--^` |
| Torque vs RPM | `indicated_torque_Nm`, `brake_torque_Nm`, `wheel_torque_Nm` | Same 3-series convention |
| VE vs RPM | `volumetric_efficiency_atm`, `volumetric_efficiency_plenum` | 2 line series, with the existing 100% reference line |
| IMEP/BMEP vs RPM | `imep_bar`, `bmep_bar` | 2 line series |
| Plenum pressure vs RPM | `plenum_pressure_bar` | 1 line, with horizontal reference line at 1 bar |
| Restrictor mdot vs RPM | `restrictor_mdot * 1000` (g/s) | 1 line, with red shaded band where `restrictor_choked == true` |

**Live behavior**: each chart appends data points as `rpm_done` events arrive over the WebSocket. Empty/queued RPMs show no point yet — the curves "fill in" as RPMs complete (left-to-right or whatever order workers happen to finish). After all RPMs are in, the curves are connected with smooth lines.

**Interactivity**:
- Hover any point → tooltip with all perf-dict values for that RPM
- Click any point → loads that RPM into the `RpmDetail` panel below
- The currently selected RPM gets a highlighted marker (filled circle) on every chart

### WorkersStrip (middle region, ~15% viewport, hidden when no sweep is running)

Horizontal row of `WorkerTile` cards, one per RPM in the sweep. Each tile shows:

- **RPM number** (large, bold, top of card)
- **rpm_index** (tiny, top-right)
- **Status icon + text**: `⏳ queued`, `▶ running`, `⚡ converged`, `✓ done`, `✗ error`
- **Current cycle / target cycles**: `cyc 5/12`
- **Convergence delta**: numeric `δ 0.0341` and a sparkline of the last N delta values
- **Elapsed seconds**: `12.4s`
- **For done tiles**: small perf summary (`P=72.2 hp`, `T=64 Nm`, `VE 107%`)
- **For running tiles**: tiny live cylinder pressure sparkline of cycle 1's last few hundred steps (sampled to ~50 points for performance)

Tiles are click-targets — clicking sets the selected RPM and updates `RpmDetail`. Queued tiles are dimmed; done tiles have a green border; errored tiles have a red border + tooltip with traceback.

### RpmDetail (bottom region, ~45% viewport, always visible)

A large detail panel for ONE selected RPM. Header has the big RPM number with a dropdown to switch + tabs across the top.

| Tab | What's shown |
|---|---|
| **Cylinders** | A row of 4 small cylinder pressure traces (one per cylinder) + a large overlay chart showing all 4 on the same axes. Pressure (bar) vs crank angle. Click a small one to enlarge. |
| **P-V** | Per-cylinder P-V indicator diagrams. Log-log toggle. The selected cylinder's diagram is large; the others are thumbnails along the side. |
| **Pipes** | A grid of pipe pressure traces at midpoint: 4 intake runners, 4 exhaust primaries, 2 exhaust secondaries, 1 collector. Each panel shows pressure (bar) and velocity (m/s) on twin axes. Hovering syncs a vertical crank-angle line across all panels. |
| **Plenum** | Plenum pressure and temperature vs crank angle, two stacked charts. Reference line at atmospheric pressure. |
| **Restrictor** | Mass flow vs crank angle, with a red band where flow is choked. Scalar readout: total intake mass per cycle (g), choked %. |
| **Cycle Convergence** | Table + chart of cycle-by-cycle convergence delta + per-cylinder p_at_IVC values. Useful for "did it actually converge?" inspection. |

**Data source**: when the user selects an RPM, the React app checks if it has the `SimulationResults` cached in the Zustand store. If not, it fetches `GET /api/sweeps/current/results/{rpm}` (or `/api/sweeps/{id}/results/{rpm}` for past sweeps), caches the response keyed by `(sweep_id, rpm)`, and renders.

For the live monitor, this means: as soon as an RPM finishes, you can click its tile and immediately see all the cylinder/pipe/plenum traces. The fetch happens once per RPM per session.

### SweepListSidebar (right edge, collapsible)

A vertical list of past sweeps, newest at the top. Each entry: timestamp, RPM range, duration, n_workers. Clicking → confirms ("Switch to this sweep? Current view will be replaced.") → loads via `GET /api/sweeps/{id}` → entire app view updates. Sidebar collapses to a thin rail when not in use (Tailwind transition).

---

## Section 5 — Visual Design Language

The aesthetic target is a **technical instrument**, not a consumer SaaS dashboard. Think **F1 telemetry, Bloomberg terminal, Linear, Cursor, Vercel** — tools built by engineers for engineers, where information density and typographic discipline matter more than rounded corners and soft gradients. The CBR600RR is a 13,000-RPM race engine; the GUI should feel like it has the same energy.

### Anti-patterns to avoid (the "AI slop" reflex)

| ❌ Don't | ✅ Do instead |
|---|---|
| Symmetric, soft, rounded "card" everything | Asymmetric grid layouts, sharp 1-2px borders, tight corners (`rounded-sm` max for most elements) |
| Big pastel gradients on buttons | Solid single-color accent on a dark surface |
| Excessive whitespace | Tight, data-dense layouts — every pixel earns its place |
| Generic "Inter for everything" | Distinctive type pairing: `Inter Tight` for UI, `JetBrains Mono` for ALL numeric values |
| Floating action buttons, hero sections | Tools-bar style, no decorative chrome |
| Smooth gradient charts with shadow drops | Crisp 1px stroke charts on a flat dark background |
| Rainbow color coding | A small, deliberate palette (5-6 colors max, all chosen for a reason) |
| Skeleton loaders that pulse | Indeterminate progress that *means* something (cycle count, elapsed) |
| Toast notifications for everything | Status communicated in-place, never as floating alerts |
| Emoji icons | `lucide-react` icons, monochrome, 16px |

### Color palette

```
Background        #0A0A0B  (almost-black, very slight blue tint)
Surface           #131316  (panel background)
Surface raised    #1A1A1F  (worker tile, modal)
Border default    #25252B  (1px hairlines between regions)
Border emphasis   #3A3A42  (selected state, hover)

Text primary      #F5F5F7
Text secondary    #8B8B95
Text muted        #565660

Accent (brand)    #FF4F1F  (vermillion-red — Honda heritage, FSAE energy,
                            also semantically "active/running")
Accent dim        #B33815  (hover-darkened states)

Power (indicated) #E5484D  (red, matches existing matplotlib `r-o`)
Power (brake)     #4493F8  (blue, matches existing `b-s`)
Power (wheel)     #4493F8 + dashed stroke (matches existing `b--^`)
VE (atm)          #3DD68C  (green)
VE (plenum)       #3DD68C + dashed stroke
Restrictor mdot   #C586E8  (magenta, matches existing `m-`)
Choked band       #FF4F1F at 12% opacity (warning)

Status: queued    #565660  (text-muted; tile dim)
Status: running   #FF4F1F  (accent; tile glows)
Status: converged #FFD15C  (amber; "converged but bonus cycle pending")
Status: done      #3DD68C  (green; tile has subtle green border)
Status: error     #E5484D  (red; tile has red border + tooltip)
```

The accent (`#FF4F1F`) is the only "warm" color in the palette. It's used **sparingly** — for active states, the primary "Run Sweep" button, the running-RPM indicators in the workers strip, and the choked band. Everything else is cold neutrals + the chart-specific colors. This single-accent discipline is what makes a UI feel intentional rather than generic.

### Typography

Two typefaces, no exceptions:

- **`Inter Tight`** (variable, weights 400/500/600) — every UI text element. Slightly more condensed than regular Inter, gives the data-dense layout a tighter visual rhythm. Loaded from Google Fonts via Tailwind.
- **`JetBrains Mono`** (variable, weights 400/500) — every numeric value, every code snippet, every axis label, every cycle counter, every RPM number. Mono'd numbers tabulate naturally across worker tiles and table rows.

**Type scale** (Tailwind classes):

```
text-[10px]  uppercase tracking-wider  → micro labels ("RPM", "WORKERS", "STATUS")
text-xs                                 → secondary labels, axis tick text
text-sm                                 → body, table data
text-base                               → primary content
text-lg      font-medium                → section headers
text-2xl     font-semibold              → tile RPM numbers, dialog headers
text-4xl     font-mono font-medium      → headline metric readouts (P_brk, etc.)
text-6xl     font-mono font-medium      → the ONE big number on the topbar (ETA)
```

### Information density rules

- **Tile padding: `p-2.5` to `p-3` max.** Worker tiles pack tight against each other with thin borders.
- **Row heights: `h-7` for table rows, `h-6` for compact lists.** No 64px-tall list items.
- **Border radius: `rounded` (4px) max** on most elements. Modal and dialog get `rounded-md` (6px). NEVER `rounded-lg` or `rounded-xl` for primary surfaces — that's the AI-slop tell.
- **Gaps: `gap-1.5` between tiles, `gap-2` between sections, `gap-3` between major regions.**

### Charts

Charts are 80% of what the user looks at. They must look distinctive, not like a default Recharts demo.

- **No background grid lines** by default — only a 1px horizontal baseline at major axis values, drawn in `border-default`.
- **Single 1.5px stroke per series**, no fill, no markers except small filled circles (3px) at data points. Thicker strokes on hover/selection.
- **Axis text in `text-secondary` mono, 10px**, no rotation, minimal tick density.
- **No legends inside the plot area** — legends live as a separate row above the chart, in `text-xs uppercase tracking-wider`.
- **Tooltips: dark surface, 1px border, mono font, table-style key:value rows.** Right-aligned numeric values.
- **Y-axis label vertical along the left edge**, in `text-[10px] uppercase tracking-wider`.
- **Selected RPM marker**: a vertical 1px line across all stacked charts at the selected RPM, plus a filled accent-colored circle on the data point in each chart.

### Iconography

- **`lucide-react`** for every icon. Monochrome, 16px default, 14px for inline. Stroke width 1.5.
- The icons we need: `Play`, `Square`, `FolderOpen`, `Settings`, `AlertTriangle`, `Check`, `Loader2`, `ChevronRight`, `Activity`.

### Animation principles

- **Functional only.** Animations communicate state change (a new RPM finished → its data point fades into the chart over 200ms). Decorative animations are forbidden.
- **`duration-150` to `duration-200` max** for any UI transition.
- **`ease-out`** for state changes, never `ease-in-out`.
- **No layout shift on data updates.** Worker tiles stay in fixed positions. Charts re-render smoothly without resizing.
- **Skeleton loaders are forbidden** — empty states show meaningful placeholder text.

### Reference points

**Look at:**
- **Linear** — tight tile layouts, sidebar, type discipline
- **Vercel dashboard** — chart restraint, dark theme, accent discipline
- **Cursor IDE** — tool chrome, info density, status bar
- **Bloomberg Terminal** — extreme "every pixel is data"
- **Existing matplotlib output in `postprocessing/visualization.py`** — chart palette and engineering plot feel

**Do NOT look at:**
- Material Design demos
- "Modern dashboard" template marketplaces
- Notion, Figma, or any "creative tool" UI
- Stripe Dashboard

### Implementation note: when frontend-design is invoked

When we get to the implementation plan and start building React components, the implementation will invoke `frontend-design` as a sub-skill. The agent will use this section as its **brief**:

> "Build [component] to fit a technical instrument aesthetic per the visual design language section of `2026-04-08-engine-sim-gui-v1-design.md`. Use the specific colors, type scale, density rules, and chart conventions defined there. The reference points are Linear, Vercel, Cursor, and Bloomberg Terminal — NOT Material Design or generic SaaS dashboards."

That's the explicit hand-off. The visual identity is decided here in the spec, so frontend-design has a real brief to execute against rather than reinventing it from scratch.

---

## Section 6 — Sweep Persistence

### Storage location

`sweeps/` directory at the project root. Created on first sweep run if it doesn't exist. Auto-saved files only.

```
1d/
├── engine_simulator/
├── sweeps/                                                    ← new
│   ├── 2026-04-08T17-12-33_6000-13000_step1000_12cyc.json
│   ├── 2026-04-08T18-23-04_6000-13000_step1000_12cyc.json
│   └── 2026-04-09T09-15-22_6000-13000_step250_12cyc.json
└── ...
```

Filename schema: `{ISO timestamp with - instead of :}_{rpm_start}-{rpm_end}_step{rpm_step}_{n_cycles}cyc.json`. Sortable by date alphabetically, descriptive at a glance, safe across all filesystems (no `:` characters).

### File format

A single JSON document per sweep. Schema:

```jsonc
{
  "schema_version": 1,
  "sweep_id": "2026-04-08T18-23-04_6000-13000_step1000_12cyc",
  "metadata": {
    "started_at": "2026-04-08T18:23:04.123Z",
    "completed_at": "2026-04-08T18:28:31.847Z",
    "duration_seconds": 327.7,
    "host": "macbook-pro.local",
    "python_version": "3.9.6",
    "n_workers_requested": 8,
    "n_workers_effective": 8,
    "config_name": "cbr600rr.json",
    "git_status": null    // reserved for future
  },
  "sweep_params": {
    "rpm_start": 6000, "rpm_end": 13000, "rpm_step": 1000,
    "n_cycles": 12,
    "rpm_points": [6000, 7000, 8000, 9000, 10000, 11000, 12000, 13000]
  },
  "engine_config": {
    // Full snapshot of the EngineConfig used. Mirrors the existing
    // engine_simulator/config/cbr600rr.json structure exactly.
    "p_ambient": 101325.0,
    "T_ambient": 300.0,
    "n_cylinders": 4,
    "firing_order": [1, 2, 4, 3],
    "firing_interval": 180.0,
    "drivetrain_efficiency": 1.0,
    "cylinder": { /* ... */ },
    "intake_valve": { /* ... */ },
    "exhaust_valve": { /* ... */ },
    "combustion": { /* ... */ },
    "intake_pipes": [ /* ... */ ],
    "exhaust_primaries": [ /* ... */ ],
    "exhaust_secondaries": [ /* ... */ ],
    "exhaust_collector": { /* ... */ },
    "plenum": { "volume": 0.0015 },
    "restrictor": { "diameter": 0.020, "Cd": 0.85 },
    "simulation": { /* ... */ }
  },
  "perf": [
    {
      "rpm": 6000.0,
      "indicated_power_hp": 65.0,
      // ... full perf dict, exactly as run_single_rpm returns it ...
      "wheel_torque_Nm": 64.7,
      "drivetrain_efficiency": 1.0,
      "rpm_index": 0,
      "elapsed_seconds": 142.3,
      "step_count": 13068,
      "converged": true
    }
    // ... one entry per RPM in rpm_points order ...
  ],
  "results_by_rpm": {
    "6000": {
      // The full SimulationResults for this RPM's recorded last cycle.
      // Lists, not numpy arrays — JSON-serializable.
      "theta_history": [0.0, 0.052, /* ... */, 720.0],
      "dt_history": [0.000052, 0.000051, /* ... */],
      "cylinder_data": {
        "0": { "theta": [...], "pressure": [...], "temperature": [...],
               "velocity": [...], "density": [...] },
        "1": { /* ... */ },
        "2": { /* ... */ },
        "3": { /* ... */ }
      },
      "pipe_probes": {
        "intake_runner_1_mid": { /* same shape as cylinder_data entries */ },
        // ... all 11 pipes ...
        "exhaust_collector_mid": { /* ... */ }
      },
      "plenum_pressure":    [101325.0, /* ... */],
      "plenum_temperature": [300.0, /* ... */],
      "restrictor_mdot":    [0.012, /* ... */],
      "restrictor_choked":  [false, /* ... */]
    }
    // ... one entry per RPM ...
  }
}
```

### Size estimates

Per RPM, with default 30-point pipes and ~6000 steps in the recorded cycle: ~700 KB JSON. For an 8-RPM sweep: ~5-6 MB. For a 30-RPM high-def sweep: ~20 MB. Disk usage at one sweep per day for a year: ~2-7 GB. Acceptable.

If file size becomes a concern later: gzip the JSON (3-5× smaller) or switch to msgpack-numpy. NOT in v1.

### Save lifecycle

1. Sweep starts → `SweepManager` creates an in-memory `LiveSweepState`
2. `RPMDoneEvent` arrives → perf dict and `SimulationResults` get written into `LiveSweepState`
3. After all RPMs complete:
   - `persistence.save_sweep(live_state, sweeps_dir)` is called
   - Builds the JSON document above
   - **Writes atomically**: write to `<filename>.tmp`, fsync, rename to `<filename>`
   - Returns the filename
4. Server broadcasts `sweep_complete` WebSocket message
5. React app updates its `available_sweeps` list

**No incremental saves during the sweep.** A crash mid-sweep loses the sweep. Acceptable because sweeps are short enough to re-run, the live view IS the in-progress record, and incremental saves complicate the file format.

### Load lifecycle

1. User clicks "Load past sweep" → React shows the dropdown from `available_sweeps`
2. User picks one → `GET /api/sweeps/{id}`
3. Server reads the JSON file → parses → creates an immutable `LoadedSweepState` → broadcasts a `snapshot` WS message with the loaded data
4. React app's `eventReducer` treats this snapshot exactly like a fresh-tab snapshot: replaces all sweep state
5. Workers strip is empty (loaded sweeps have no active workers); all RPM tiles show `done` state with full perf info
6. Detail-tab clicks render instantly from the in-memory loaded data

### Schema versioning

The `schema_version: 1` field is the load-time guard. Future incompatible changes bump the version. The loader rejects unknown future versions with a clear error.

### Self-contained files

A sweep file is fully self-contained — it includes the `engine_config` snapshot, so a teammate can load your sweep without needing your config file. v3 "share with teammates" foundation.

---

## Section 7 — Solver Process Integration

The integration seam is the existing `EventConsumer` protocol from today's parallelization work. **Zero changes to `parallel_sweep.py` or `orchestrator.py`** are needed.

### The GUIEventConsumer

```python
# engine_simulator/gui/gui_event_consumer.py
import asyncio
from engine_simulator.simulation.parallel_sweep import (
    ProgressEvent, RPMStartEvent, CycleDoneEvent,
    ConvergedEvent, RPMDoneEvent, RPMErrorEvent,
)


class GUIEventConsumer:
    """EventConsumer impl that drains events into an asyncio queue.

    The SweepManager owns one of these per active sweep. The WebSocket
    pump task drains the queue and broadcasts to all connected clients.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._queue: asyncio.Queue = asyncio.Queue()

    def handle(self, event: ProgressEvent) -> None:
        # Called from a worker callback (which runs on a non-asyncio thread
        # because ParallelSweepRunner.run() blocks the calling thread).
        # We need to schedule the put onto the asyncio event loop from this
        # non-asyncio context.
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        except RuntimeError:
            # Loop is closed; sweep is shutting down. Drop the event.
            pass

    def close(self) -> None:
        # Called once at the end of ParallelSweepRunner.run().
        # Signal end-of-stream to the pump task with a sentinel.
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, None)
        except RuntimeError:
            pass

    @property
    def queue(self) -> asyncio.Queue:
        return self._queue
```

This is exactly the kind of `EventConsumer` the protocol was designed for in today's work.

### The SweepManager

Owns the sweep lifecycle: start, drain events, save, stop. Single source of truth for the currently-running (or last-finished) sweep.

```python
# engine_simulator/gui/sweep_manager.py
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator
from engine_simulator.gui.gui_event_consumer import GUIEventConsumer
from engine_simulator.gui.persistence import save_sweep


@dataclass
class LiveSweepState:
    """Single source of truth for the currently-running (or last-finished) sweep."""
    sweep_id: str
    status: str                                  # "running" | "complete" | "error" | "stopped"
    config: EngineConfig
    config_name: str
    rpm_points: list
    n_cycles: int
    n_workers: int
    started_at: str
    completed_at: Optional[str] = None
    rpms: dict = field(default_factory=dict)     # rpm -> per-rpm state
    results_by_rpm: dict = field(default_factory=dict)
    sweep_results: list = field(default_factory=list)


class SweepManager:
    """Owns sweep lifecycle for the GUI: start, stop, drain events, save."""

    def __init__(self, loop, sweeps_dir, broadcast_fn):
        self._loop = loop
        self._sweeps_dir = sweeps_dir
        self._broadcast_fn = broadcast_fn
        self._current: Optional[LiveSweepState] = None
        self._sweep_task = None
        self._drain_task = None
        self._consumer: Optional[GUIEventConsumer] = None
        # ParallelSweepRunner.run() is blocking, so we run it in a thread.
        # ONE thread, used only for the runner. The runner internally spawns
        # the actual ProcessPoolExecutor for the workers.
        self._runner_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="sweep-runner",
        )

    async def start_sweep(self, params: dict) -> str:
        """Start a sweep. Returns the sweep_id. Raises if one is already running."""
        if self._current is not None and self._current.status == "running":
            raise RuntimeError("A sweep is already running. Stop it first.")

        config = EngineConfig.from_json(params["config_name"])

        import numpy as np
        rpm_points = list(np.arange(
            params["rpm_start"],
            params["rpm_end"] + params["rpm_step"] / 2,
            params["rpm_step"],
        ))
        rpm_points = [float(r) for r in rpm_points]

        sweep_id = self._make_sweep_id(params)
        self._current = LiveSweepState(
            sweep_id=sweep_id, status="running", config=config,
            config_name=params["config_name"], rpm_points=rpm_points,
            n_cycles=params["n_cycles"], n_workers=params["n_workers"],
            started_at=_iso_now(),
            rpms={float(rpm): {"status": "queued", "rpm_index": idx}
                  for idx, rpm in enumerate(rpm_points)},
        )

        self._consumer = GUIEventConsumer(self._loop)
        self._drain_task = asyncio.create_task(self._drain_events())
        self._sweep_task = asyncio.create_task(self._run_sweep_in_thread(params))

        return sweep_id

    async def _run_sweep_in_thread(self, params: dict):
        try:
            await self._loop.run_in_executor(
                self._runner_executor,
                self._run_sweep_blocking,
                params,
            )
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
        except Exception as exc:
            import traceback
            self._current.status = "error"
            await self._broadcast_fn({
                "type": "sweep_error",
                "error_msg": str(exc),
                "traceback": traceback.format_exc(),
            })

    def _run_sweep_blocking(self, params: dict):
        """Runs in the runner thread. Calls the existing SimulationOrchestrator unchanged."""
        sim = SimulationOrchestrator(self._current.config)
        sweep_results = sim.run_rpm_sweep(
            rpm_start=params["rpm_start"],
            rpm_end=params["rpm_end"],
            rpm_step=params["rpm_step"],
            n_cycles=params["n_cycles"],
            verbose=False,
            n_workers=params["n_workers"],
            consumer=self._consumer,             # ← the integration seam
        )
        self._current.sweep_results = sweep_results
        self._current.results_by_rpm = dict(sim.results_by_rpm)

    async def _drain_events(self):
        """Background task: drain GUIEventConsumer.queue and update state."""
        assert self._consumer is not None
        while True:
            event = await self._consumer.queue.get()
            if event is None:        # sentinel from .close()
                return
            self._apply_event(event)
            await self._broadcast_event(event)

    def _apply_event(self, event):
        """Mutate self._current.rpms based on the event type."""
        # ... full implementation in plan ...

    async def stop_sweep(self):
        if self._current is None or self._current.status != "running":
            return
        if self._sweep_task is not None:
            self._sweep_task.cancel()
        self._current.status = "stopped"
        await self._broadcast_fn({
            "type": "sweep_complete",
            "sweep_id": self._current.sweep_id,
            "stopped": True,
        })
```

### Threading model

| Thread / process | Purpose | Code |
|---|---|---|
| **Asyncio main thread** | FastAPI server, WebSocket pump, REST handlers, SweepManager orchestration, drain task | `gui/server.py`, `routes_*`, `sweep_manager.py` |
| **Sweep runner thread** (1) | Blocks inside `ParallelSweepRunner.run()` for the duration of the sweep | `_runner_executor` (1-thread `ThreadPoolExecutor`) |
| **Worker processes** (N) | The actual solver, fresh `SimulationOrchestrator` per worker. Identical to today. | `ParallelSweepRunner` → `ProcessPoolExecutor(spawn)` |
| **Manager process** (1) | `multiprocessing.Manager` hosting the cross-process queue. Identical to today. | `ParallelSweepRunner.run()` |

**Why a runner thread, not direct asyncio integration:** `ParallelSweepRunner.run()` is a blocking call (`with ProcessPoolExecutor(...)` and `for future in as_completed(futures)`). Wrapping it in a thread is the simplest way to keep the asyncio loop responsive. The runner thread doesn't do CPU work — it just blocks on worker results — so a single thread is fine.

**Why `call_soon_threadsafe`:** the consumer's `handle()` is called from inside the runner thread. We need to push events onto an asyncio queue that lives on the main asyncio loop. `call_soon_threadsafe` is the canonical primitive for cross-thread → asyncio communication; without it, you get races.

### Bit-identity guarantee

Because the GUI calls `sim.run_rpm_sweep(...)` with the same arguments the CLI does (just substituting `consumer=GUIEventConsumer(...)` for `consumer=CLIEventConsumer(...)`), and because both consumers are pure observers (read-only), the numerical output is **bit-identical** to a CLI sweep with the same parameters. Layer 1 testing makes this falsifiable.

### Stop-mid-sweep cleanup

When the user clicks Stop, the asyncio task gets cancelled. The cancellation propagates to `await loop.run_in_executor(...)`, raising `CancelledError`. The runner thread's `ProcessPoolExecutor` context manager catches the parent exception and calls `pool.shutdown(wait=False, cancel_futures=True)`, killing all worker processes. The `Manager` process exits via `manager.shutdown()` in the runner's `finally` block.

A small race: events emitted between "user clicked Stop" and "workers actually died" still get drained. That's fine — the React app sees them and records partial data. Partial sweeps are NOT saved to disk in v1.

---

## Section 8 — Testing Strategy

Four-layer model adapted from the parallelization spec.

### Layer 1 — Numerical equivalence (the keystone)

`tests/test_gui_sweep_equivalence.py`

A sweep run through `SweepManager` (the GUI's path) must produce **bit-identical** perf dicts compared to a CLI sweep with the same parameters.

```python
def test_gui_sweep_matches_cli_sweep_bit_identical():
    """A sweep run via the GUI's SweepManager must produce bit-identical
    perf dicts compared to a CLI sweep with the same parameters."""
    config = EngineConfig()
    params = {
        "rpm_start": 8000, "rpm_end": 10000, "rpm_step": 1000,
        "n_cycles": 4, "n_workers": 2, "config_name": "cbr600rr.json",
    }

    cli_sim = SimulationOrchestrator(config)
    cli_results = cli_sim.run_rpm_sweep(
        rpm_start=8000, rpm_end=10000, rpm_step=1000,
        n_cycles=4, verbose=False, n_workers=2,
    )

    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    received_messages = []
    async def fake_broadcast(msg): received_messages.append(msg)
    manager = SweepManager(loop, sweeps_dir="/tmp/test_sweeps_gui",
                           broadcast_fn=fake_broadcast)
    sweep_id = loop.run_until_complete(manager.start_sweep(params))
    loop.run_until_complete(manager._sweep_task)
    loop.close()
    gui_results = manager.current.sweep_results

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

### Layer 2 — Persistence round-trip

`tests/test_gui_persistence.py`

A `LiveSweepState` saved to JSON and loaded back must produce the same data:

```python
def test_save_load_roundtrip_perf_dicts_bit_identical(): ...
def test_save_load_roundtrip_results_arrays_bit_identical(): ...
def test_save_atomic_write_does_not_leave_corrupt_file_on_crash(): ...
def test_load_unknown_schema_version_raises_clear_error(): ...
def test_load_corrupt_json_raises_clear_error(): ...
```

### Layer 3 — Plumbing tests (independent of solver math)

Fast, no real solver, no real browser.

**`tests/test_gui_event_consumer.py`** — `GUIEventConsumer.handle()` correctly puts events on the asyncio queue from a non-asyncio thread. `close()` puts the sentinel.

**`tests/test_gui_sweep_manager.py`** — `SweepManager` orchestration tests using a stub solver:
- `start_sweep()` raises if a sweep is already running
- Drain task processes events in order
- `_apply_event` correctly mutates `LiveSweepState.rpms` for each event type
- `stop_sweep()` cancels the runner thread cleanly
- After successful completion, `save_sweep` is called and `sweep_complete` is broadcast
- After error, `sweep_error` is broadcast and state is `error`

**`tests/test_gui_routes_api.py`** — REST endpoint integration tests using FastAPI's `TestClient`:
- `GET /api/health` returns `{status: "ok"}`
- `GET /api/configs` lists files in `engine_simulator/config/`
- `POST /api/sweep/start` with valid params returns 200 + sweep_id; with missing params returns 422
- `POST /api/sweep/start` while a sweep is already running returns 409 Conflict
- `POST /api/sweep/stop` returns 200 even when no sweep is running (idempotent)
- `GET /api/sweeps` returns the list of files in `sweeps/`
- `GET /api/sweeps/{id}` returns the loaded sweep JSON
- `GET /api/sweeps/{id}` with a nonexistent ID returns 404

**`tests/test_gui_routes_ws.py`** — WebSocket protocol tests using FastAPI's `TestClient` WebSocket support:
- Connecting to `/ws/events` immediately receives a `snapshot` message
- Snapshot when no sweep running has `sweep: null` and an `available_sweeps` list
- After `start_sweep` is triggered, subsequent connections get a snapshot with the running sweep
- Synthetic events pushed through the broadcast fn are received by all connected clients in order
- A client disconnect doesn't affect other connected clients
- Reconnect after disconnect receives a fresh snapshot

**`tests/test_gui_snapshot.py`** — `snapshot.py` correctly serializes a `LiveSweepState`. Edge cases: no sweep, all-queued, mid-flight, complete, one errored RPM.

### Layer 4 — Manual smoke test (one-time, before merging)

Twelve human steps to verify the whole stack end-to-end:

```
1. Start the server:
   $ python -m engine_simulator.gui
   Expected: terminal prints "Server started on http://localhost:8765/",
             default browser opens to that URL automatically.

2. The app loads. Verify:
   - Top bar shows "Idle"
   - Sweep curves show "No sweep loaded" placeholder
   - Workers strip is hidden
   - RpmDetail shows "No RPM selected" placeholder

3. Click "Run Sweep". A modal opens.
   - RPM start: 8000, end: 10000, step: 1000, cycles: 4, workers: 2
   - Config: cbr600rr.json (default)
   - Click Start.

4. Watch the live monitor:
   - Workers strip appears with 3 tiles (8000, 9000, 10000)
   - 2 tiles immediately show "running" (n_workers=2)
   - 1 tile shows "queued"
   - As cycles complete, the cycle counter and delta sparkline update
   - Sweep curves remain empty (no RPMs done yet)
   - First RPM to finish: tile flips to "done" with green border + perf summary
                          its data point appears on power/torque/VE charts
                          queued tile flips to "running"
   - All RPMs eventually finish; workers strip shows all "done"
   - Sweep curves show 3 data points each, smoothly connected

5. Click an RPM tile (e.g., 8000):
   - RpmDetail panel updates: "Selected: 8000 RPM"
   - Cylinders tab shows 4 small + 1 overlay cylinder pressure traces
   - Click P-V tab: P-V indicator diagrams render
   - Click Pipes tab: 11 pipe probes render in a grid
   - Click Plenum, Restrictor, Cycle Convergence: all render with data

6. Verify auto-save:
   - Open a terminal: ls -la sweeps/
   - Expected: a new file named like "2026-04-08T..._8000-10000_step1000_4cyc.json"
   - Verify file size is reasonable (~1-3 MB for a 3-RPM sweep)
   - cat the file | jq '.metadata, .sweep_params, .perf[0].brake_power_hp'
   - Expected: valid JSON with sane metadata, matching sweep_params,
               first RPM's brake power matching what the GUI showed.

7. Reload the browser tab:
   - Expected: same sweep is still loaded (not lost on refresh)
   - All RPMs in their final state, all data still present

8. Click "Load past sweep" → pick the auto-saved file:
   - Expected: confirmation → confirm → app loads the past sweep
   - Same data, same plots, identical to step 7

9. Click "Run Sweep" again with the same params:
   - Expected: new sweep starts, replaces the loaded one in the live view
   - Live monitor activates, plays out the new sweep
   - When done: a SECOND file appears in sweeps/ with a later timestamp
   - The first sweep is still on disk

10. Click Stop in the middle of a fresh sweep:
    - Expected: confirmation → confirm
    - All running workers' tiles flip to "stopped"
    - Sweep status in topbar shows "Stopped"
    - No sweep file is saved (partial sweeps are not auto-saved in v1)

11. Trigger an error: edit a config file to have an invalid value (e.g., negative bore),
    save, and start a sweep with it.
    - Expected: failing RPM's tile flips to red with the error type
    - Traceback visible on hover
    - Other RPMs continue running
    - When sweep completes, it's still auto-saved

12. Close the browser tab:
    - Expected: server keeps running for ~10 seconds, then shuts down
                (or stays alive if you opened the browser again within 10s)
    - Terminal prints "Server stopped" cleanly
```

### Anti-tests (deliberately not tested)

- **Visual regression / pixel-diff tests.** Out of scope for v1; manual smoke test is the gate.
- **Cross-browser compatibility.** v1 targets the user's default macOS browser.
- **Multiple simultaneous browser tabs.** Should work but not explicitly tested.
- **Network failure / WebSocket reconnect.** Logic is implemented but tested only manually.
- **Performance under load.** Real sweeps produce ~10 events per second per worker, comfortably below saturation.

---

## Decision Log

1. **Two-spec split: v1 = Live + Report, v2 = Config Editor** — keeps the first cycle small enough to land quickly. Surfaces 1 and 2 share components naturally; surface 3 is a separate UI surface.
2. **Local laptop, FastAPI + React + Tailwind** — user requested React+Tailwind for polish; FastAPI is the natural Python backend. Localhost-only.
3. **One-command launch** — `python -m engine_simulator.gui` starts server + opens browser. No manual coordination.
4. **Mission Control layout** — sweep curves on top (always visible), workers strip in middle (live only), RpmDetail panel at bottom, sidebar for past sweeps. Gives "all information possible" without modal navigation.
5. **Auto-save every sweep to `sweeps/`** — zero ceremony, sweeps are always recoverable, foundation for future "compare two runs" feature.
6. **JSON file format with full self-contained engine_config snapshot** — files are debuggable with `jq`, shareable with teammates, and loadable into v2's config editor.
7. **`GUIEventConsumer` is the only integration seam** — uses the existing `EventConsumer` protocol from today's parallelization. Zero changes to solver code.
8. **Sweep runner in a dedicated thread, asyncio loop in main thread** — `ParallelSweepRunner.run()` is blocking, so it can't run directly on the asyncio loop. One thread keeps the loop responsive.
9. **Layer 1 equivalence test for the GUI path** — guarantees `python -m engine_simulator.main sweep --workers 2` produces bit-identical results to `SweepManager.start_sweep(...)` with the same params.
10. **Visual identity pinned in the spec, executed by `frontend-design` later** — prevents the implementation phase from defaulting to generic AI-dashboard aesthetics. The spec's "Visual Design Language" section is the brief.
11. **Charts: hairline strokes, no grid, mono axes, no legend in plot area** — distinctive instrument look, not Recharts default.
12. **Partial sweeps are NOT auto-saved on stop** — would complicate file format (need `status: incomplete` flag). v1 keeps it simple.

## Implementation sequencing (handed to writing-plans)

When implementation begins, the order is:

1. Backend skeleton: FastAPI app, lifespan, browser launch, `/api/health`
2. `GUIEventConsumer` + tests
3. `SweepManager` with stub runner + tests
4. Real `SweepManager` integration (calls `SimulationOrchestrator.run_rpm_sweep`)
5. Layer 1 equivalence test (gates everything else)
6. `persistence.py` save/load + Layer 2 tests
7. REST routes (`/api/sweep/start`, `/api/sweep/stop`, `/api/sweeps`, etc.) + tests
8. WebSocket route + snapshot serialization + tests
9. Frontend scaffold: Vite + React + Tailwind + Zustand setup
10. WebSocket client + state store + event reducer
11. Top bar + Run Sweep dialog + REST client wiring
12. Sweep curves component + chart wrappers (invokes `frontend-design`)
13. Workers strip + worker tile component (invokes `frontend-design`)
14. RpmDetail panel + tabs (cylinders, P-V, pipes, plenum, restrictor, convergence)
15. Sidebar with past sweeps
16. Build helper script (`scripts/build_gui.py`)
17. End-to-end manual smoke test (Layer 4)

Each numbered step is independently verifiable. Steps 1-8 leave the codebase with a working backend and zero frontend (testable via `curl` and `wscat`). Steps 9-16 build the frontend incrementally on top.
