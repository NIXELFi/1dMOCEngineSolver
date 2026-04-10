# Dyno Playback Tab — Design Spec

## Overview

A new "Dyno" tab that plays back completed sweep data as a smooth, animated dyno pull. RPM climbs continuously with interpolated values driving live numeric gauges and progressively-drawn performance charts. Users can play, pause, scrub, and adjust speed.

This is a **frontend-only feature** — no new backend endpoints. It consumes the existing `SweepSnapshot` and `PerfDict` data already in `sweepStore`.

## Data Source

The Dyno tab reads from whatever sweep is currently loaded in `sweepStore`. The sweep contains:

- `rpm_points: number[]` — sorted array of simulated RPM values
- `rpms: Record<string, RpmState>` — per-RPM state, each with a `perf?: PerfDict`

Only RPM points with `status === "done"` and a valid `perf` object are used. If no sweep is loaded or no RPM points have completed, the tab shows a "No sweep data available" message.

## Interpolation

Given the discrete RPM points from the sweep, the playback engine produces smooth continuous values:

- **Independent variable**: RPM, advancing from `rpm_points[0]` to `rpm_points[last]`
- **Method**: Linear interpolation between the two bracketing data points for all numeric `PerfDict` fields
- **Boolean fields** (`restrictor_choked`): Snap to the nearest RPM point's value
- **Edge behavior**: At exact data points, use the data point value directly

### Interpolated Fields (all from `PerfDict`)

| Field | Unit | Display Name |
|-------|------|--------------|
| `rpm` | RPM | RPM |
| `indicated_power_hp` | hp | Indicated Power |
| `indicated_torque_Nm` | Nm | Indicated Torque |
| `brake_power_hp` | hp | Brake Power |
| `brake_torque_Nm` | Nm | Brake Torque |
| `wheel_power_hp` | hp | Wheel Power |
| `wheel_torque_Nm` | Nm | Wheel Torque |
| `drivetrain_efficiency` | % | Drivetrain Eff. |
| `imep_bar` | bar | IMEP |
| `bmep_bar` | bar | BMEP |
| `fmep_bar` | bar | FMEP |
| `volumetric_efficiency_atm` | % | VE (Atm) |
| `volumetric_efficiency_plenum` | % | VE (Plenum) |
| `intake_mass_per_cycle_g` | g | Intake Mass/Cycle |
| `plenum_pressure_bar` | bar | Plenum Pressure |
| `restrictor_mdot` | g/s | Restrictor Flow |
| `restrictor_choked` | bool | Choked |

## Playback Timeline

- **Timeline axis**: RPM (not wall-clock time)
- **Default pull duration**: 10 seconds to traverse the full RPM range
- **Speed multipliers**: 0.5x, 1x, 2x (adjustable during playback)
- **Animation driver**: `requestAnimationFrame` loop. Each frame computes `elapsed_ms * speed`, maps to an RPM position, interpolates all fields, and writes to `dynoStore`
- **Frame update**: Store updates trigger React re-renders via Zustand selectors

### Transport Controls

| Control | Behavior |
|---------|----------|
| **Play** | Start/resume advancing RPM from current position |
| **Pause** | Freeze at current RPM position |
| **Reset** | Return to `rpm_points[0]`, pause |
| **Scrub slider** | Drag to set RPM position directly. Dragging auto-pauses. Release does not auto-resume |
| **Speed buttons** | Toggle between 0.5x / 1x / 2x. Active speed highlighted |

## Gauge Panel

Top section of the Dyno tab. A responsive grid of gauge cards showing live interpolated values.

### GaugeCard Component

Each card displays:
- **Label**: Parameter name (e.g. "Brake Power")
- **Value**: Large numeric readout, updating each frame. Formatted to appropriate precision (powers: 1 decimal, pressures: 3 decimals, percentages: 1 decimal)
- **Unit**: Suffix label (hp, Nm, bar, g/s, %)
- **Range bar**: Thin horizontal bar showing where the current value sits within the min/max range observed across the full sweep

### Gauge Layout

Gauges are arranged in a responsive grid grouped by category:

**Row 1 — Primary** (larger cards):
- RPM (extra-large, prominent)
- Brake Power (hp)
- Brake Torque (Nm)

**Row 2 — Indicated & Wheel**:
- Indicated Power (hp)
- Indicated Torque (Nm)
- Wheel Power (hp)
- Wheel Torque (Nm)

**Row 3 — Efficiency**:
- VE Atmospheric (%)
- VE Plenum (%)
- Drivetrain Efficiency (%)

**Row 4 — MEP**:
- IMEP (bar)
- BMEP (bar)
- FMEP (bar)

**Row 5 — Intake System**:
- Plenum Pressure (bar)
- Restrictor Flow (g/s)
- Intake Mass/Cycle (g)
- Restrictor Choked (on/off indicator light, not a numeric gauge)

### Choked Indicator

The restrictor choked status is displayed as a small indicator dot/badge rather than a numeric readout:
- **Off**: Dim/muted dot with "UNCHOKED" label
- **On**: Accent-colored (orange) dot with "CHOKED" label

## Progressive Charts

Bottom section. Six charts that draw in as RPM advances, using the existing `LineChart.tsx` wrapper for visual consistency with the Simulation tab.

### Chart Definitions

| # | Title | Y-Axis | Series |
|---|-------|--------|--------|
| 1 | Power | hp | Indicated (solid), Brake (solid), Wheel (dashed) |
| 2 | Torque | Nm | Indicated (solid), Brake (solid), Wheel (dashed) |
| 3 | Volumetric Efficiency | % | Atmospheric (solid), Plenum (solid) |
| 4 | Mean Effective Pressure | bar | IMEP (solid), BMEP (solid), FMEP (dashed) |
| 5 | Plenum Pressure | bar | Single line |
| 6 | Restrictor Flow | g/s | Single line, with choked zone shading |

### Progressive Drawing Behavior

- Each chart's X-axis spans the full RPM range (fixed, not zooming)
- Data is rendered only up to the current playback RPM — the lines grow rightward
- A **vertical dashed line** in accent color marks the current playhead position
- The data shown is the actual discrete sweep points that have been "passed" so far, plus one interpolated point at the current RPM for smooth line extension
- When playback completes or is reset to show full data, the playhead line disappears
- Charts are not interactive during playback (no click-to-select-RPM behavior)

### Layout

Responsive grid matching existing `SweepCurves`: `grid-cols-1 lg:grid-cols-2 xl:grid-cols-3`.

## Transport Bar

Horizontal strip positioned between the gauge panel and the charts.

### Layout (left to right)

1. **Play/Pause button** — single toggle button with `Play`/`Pause` icon from lucide-react
2. **Reset button** — `RotateCcw` icon
3. **Scrub slider** — flex-1, full remaining width. Thumb shows current RPM as a tooltip/label
4. **RPM readout** — current RPM value (numeric, right-aligned)
5. **Speed buttons** — three buttons: `0.5x` | `1x` | `2x`, active one highlighted with accent

### Styling

- Height: ~40px, matching TopBar/TabBar proportions
- Background: `bg-surface`, bottom border `border-border-default`
- Buttons: same style as existing UI controls
- Slider: custom-styled to match dark theme (accent color for filled portion)

## Tab Integration

### TabBar Changes

Add a third tab to `TabBar.tsx`:

```typescript
export type ActiveTab = "simulation" | "config" | "dyno";

const TABS: TabDef[] = [
  { id: "simulation", label: "Simulation", index: "01" },
  { id: "config",     label: "Config",     index: "02" },
  { id: "dyno",       label: "Dyno",       index: "03" },
];
```

### App.tsx Changes

Render `DynoView` when `activeTab === "dyno"`.

## State Management

### `dynoStore.ts` (new Zustand store)

```typescript
interface DynoStore {
  // Playback state
  playing: boolean;
  currentRpm: number;       // continuously interpolated position
  speed: number;            // 0.5 | 1 | 2
  startedAtMs: number | null; // rAF reference timestamp
  pausedAtRpm: number | null; // RPM when last paused (for resume)

  // Derived (computed each frame, written to store for consumers)
  interpolated: PerfDict | null;

  // Computed from sweep data (set once when sweep loads)
  rpmMin: number;
  rpmMax: number;
  sweepPoints: PerfDict[];  // sorted by RPM, only "done" points
  fieldRanges: Record<string, { min: number; max: number }>; // for gauge bars

  // Actions
  loadSweepData: () => void;   // reads from sweepStore, extracts sorted perf dicts
  play: () => void;
  pause: () => void;
  reset: () => void;
  scrubTo: (rpm: number) => void;
  setSpeed: (s: number) => void;
  tick: (timestampMs: number) => void;  // called by rAF loop
}
```

### Animation Loop

- `play()` records `startedAtMs = performance.now()`, sets `playing = true`, starts `requestAnimationFrame` loop
- Each frame: `tick(timestamp)` computes elapsed time, maps to RPM via `rpmMin + (elapsed / pullDuration) * (rpmMax - rpmMin)`, clamps to `rpmMax`, interpolates all fields, writes to store
- When `currentRpm >= rpmMax`, auto-pauses at end
- `pause()` records `pausedAtRpm`, stops rAF loop
- `resume` (via `play()` when paused): adjusts `startedAtMs` so that `currentRpm` starts from `pausedAtRpm`
- `scrubTo(rpm)`: pauses, sets `currentRpm` and `pausedAtRpm`, interpolates immediately
- `reset()`: pauses, sets `currentRpm = rpmMin`, interpolates at start point

### Interpolation Function

Standalone pure function (testable):

```typescript
function interpolatePerfAtRpm(points: PerfDict[], rpm: number): PerfDict
```

- Binary search for bracketing points
- Linear lerp for all numeric fields
- Nearest-neighbor for boolean fields
- Returns a full `PerfDict` object

## File Structure

```
src/
├── state/
│   ├── configStore.ts        # MODIFIED: ActiveTab union adds "dyno"
│   └── dynoStore.ts          # NEW
├── components/
│   ├── App.tsx               # MODIFIED: render DynoView
│   ├── TabBar.tsx            # MODIFIED: add Dyno tab
│   ├── DynoView.tsx          # NEW: top-level container
│   └── dyno/
│       ├── GaugePanel.tsx    # NEW: grid of gauge cards
│       ├── GaugeCard.tsx     # NEW: single numeric readout
│       ├── TransportBar.tsx  # NEW: play/pause/scrub/speed
│       └── ProgressiveCharts.tsx  # NEW: 6-chart grid with playhead
```

## Styling

All new components follow existing conventions:
- Dark theme colors from Tailwind config (`bg-surface`, `text-text-primary`, `border-border-default`, `bg-accent`)
- Font: Inter Tight for labels, JetBrains Mono for numeric values
- Hairline 1px borders
- Icons from `lucide-react`
- No new dependencies required
