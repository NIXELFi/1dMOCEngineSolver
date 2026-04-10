# Dyno Playback Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Dyno" tab to the GUI that plays back completed sweep data as a smooth animated dyno pull with interpolated gauges and progressive charts.

**Architecture:** New `dynoStore` (Zustand) manages playback state, interpolation, and the rAF animation loop. A `DynoView` component composes `GaugePanel`, `TransportBar`, and `ProgressiveCharts` — all reading from the store. No backend changes needed.

**Tech Stack:** React 18, TypeScript, Zustand, Recharts (via existing `LineChart.tsx` wrapper), Tailwind CSS, lucide-react icons.

**Spec:** `docs/superpowers/specs/2026-04-10-dyno-playback-tab-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| NEW | `src/state/dynoStore.ts` | Playback state, interpolation, rAF loop, field ranges |
| NEW | `src/components/DynoView.tsx` | Top-level tab container composing gauges + transport + charts |
| NEW | `src/components/dyno/GaugePanel.tsx` | Responsive grid of GaugeCard components |
| NEW | `src/components/dyno/GaugeCard.tsx` | Single numeric readout with range bar |
| NEW | `src/components/dyno/TransportBar.tsx` | Play/pause/reset/scrub/speed controls |
| NEW | `src/components/dyno/ProgressiveCharts.tsx` | 6-chart grid with playhead and progressive drawing |
| MODIFY | `src/state/configStore.ts:104` | Add `"dyno"` to `ActiveTab` union |
| MODIFY | `src/components/TabBar.tsx:9-12` | Add Dyno tab entry |
| MODIFY | `src/App.tsx:37` | Render `DynoView` when `activeTab === "dyno"` |

---

### Task 1: Interpolation Logic & Dyno Store

**Files:**
- Create: `src/state/dynoStore.ts`

This is the core of the feature — the pure interpolation function and the Zustand store that drives playback.

- [ ] **Step 1: Create `src/state/dynoStore.ts` with interpolation function**

```typescript
import { create } from "zustand";
import { useSweepStore } from "./sweepStore";
import type { PerfDict } from "../types/events";

/* ========================================================================= */
/* Interpolation — pure function, no store dependency                        */
/* ========================================================================= */

/** All numeric PerfDict keys that should be linearly interpolated. */
const NUMERIC_KEYS: (keyof PerfDict)[] = [
  "rpm",
  "indicated_power_hp",
  "indicated_torque_Nm",
  "brake_power_hp",
  "brake_torque_Nm",
  "wheel_power_hp",
  "wheel_torque_Nm",
  "drivetrain_efficiency",
  "imep_bar",
  "bmep_bar",
  "fmep_bar",
  "volumetric_efficiency_atm",
  "volumetric_efficiency_plenum",
  "intake_mass_per_cycle_g",
  "plenum_pressure_bar",
  "restrictor_mdot",
];

/**
 * Linearly interpolate all numeric PerfDict fields at a given RPM.
 * Boolean fields snap to the nearest data point.
 * `points` must be sorted by RPM ascending with length >= 1.
 */
export function interpolatePerfAtRpm(
  points: PerfDict[],
  rpm: number,
): PerfDict {
  if (points.length === 0) {
    throw new Error("interpolatePerfAtRpm: empty points array");
  }

  // Clamp to range
  if (rpm <= points[0].rpm) return { ...points[0], rpm };
  if (rpm >= points[points.length - 1].rpm)
    return { ...points[points.length - 1], rpm };

  // Binary search for the right bracket
  let lo = 0;
  let hi = points.length - 1;
  while (lo < hi - 1) {
    const mid = (lo + hi) >> 1;
    if (points[mid].rpm <= rpm) lo = mid;
    else hi = mid;
  }

  const a = points[lo];
  const b = points[hi];
  const t = (rpm - a.rpm) / (b.rpm - a.rpm);

  const result: Record<string, number | boolean | undefined> = {};
  for (const key of NUMERIC_KEYS) {
    const va = a[key];
    const vb = b[key];
    if (typeof va === "number" && typeof vb === "number") {
      result[key] = va + (vb - va) * t;
    } else {
      result[key] = va ?? vb;
    }
  }

  // Boolean: snap to nearest
  result.restrictor_choked = t < 0.5 ? a.restrictor_choked : b.restrictor_choked;

  // Override rpm with the exact interpolated position
  result.rpm = rpm;

  return result as unknown as PerfDict;
}

/* ========================================================================= */
/* Field ranges — min/max across the full sweep for gauge bars               */
/* ========================================================================= */

export type FieldRanges = Record<string, { min: number; max: number }>;

function computeFieldRanges(points: PerfDict[]): FieldRanges {
  const ranges: FieldRanges = {};
  for (const key of NUMERIC_KEYS) {
    let min = Infinity;
    let max = -Infinity;
    for (const p of points) {
      const v = p[key];
      if (typeof v === "number" && Number.isFinite(v)) {
        if (v < min) min = v;
        if (v > max) max = v;
      }
    }
    if (Number.isFinite(min) && Number.isFinite(max)) {
      ranges[key] = { min, max };
    }
  }
  return ranges;
}

/* ========================================================================= */
/* Store                                                                     */
/* ========================================================================= */

/** Default pull duration in milliseconds (10 seconds at 1x speed). */
const PULL_DURATION_MS = 10_000;

export interface DynoStore {
  // Playback state
  playing: boolean;
  currentRpm: number;
  speed: number;
  /** rAF reference: wall-clock ms when play started (adjusted for resume). */
  startedAtMs: number | null;
  /** RPM position when last paused, used to compute resume offset. */
  pausedAtRpm: number | null;

  // Derived — recomputed each frame
  interpolated: PerfDict | null;

  // Sweep data (set once via loadSweepData)
  rpmMin: number;
  rpmMax: number;
  sweepPoints: PerfDict[];
  fieldRanges: FieldRanges;

  // rAF handle for cleanup
  _rafId: number | null;

  // Actions
  loadSweepData: () => void;
  play: () => void;
  pause: () => void;
  reset: () => void;
  scrubTo: (rpm: number) => void;
  setSpeed: (s: number) => void;
  tick: (timestampMs: number) => void;
}

export const useDynoStore = create<DynoStore>((set, get) => ({
  playing: false,
  currentRpm: 0,
  speed: 1,
  startedAtMs: null,
  pausedAtRpm: null,
  interpolated: null,
  rpmMin: 0,
  rpmMax: 0,
  sweepPoints: [],
  fieldRanges: {},
  _rafId: null,

  loadSweepData: () => {
    const sweep = useSweepStore.getState().sweep;
    if (!sweep) {
      set({
        sweepPoints: [],
        rpmMin: 0,
        rpmMax: 0,
        fieldRanges: {},
        interpolated: null,
        currentRpm: 0,
        playing: false,
      });
      return;
    }

    const points: PerfDict[] = [];
    for (const r of Object.values(sweep.rpms)) {
      if (r.status === "done" && r.perf) {
        points.push(r.perf);
      }
    }
    points.sort((a, b) => a.rpm - b.rpm);

    if (points.length === 0) {
      set({
        sweepPoints: [],
        rpmMin: 0,
        rpmMax: 0,
        fieldRanges: {},
        interpolated: null,
        currentRpm: 0,
        playing: false,
      });
      return;
    }

    const rpmMin = points[0].rpm;
    const rpmMax = points[points.length - 1].rpm;
    const fieldRanges = computeFieldRanges(points);
    const interpolated = interpolatePerfAtRpm(points, rpmMin);

    set({
      sweepPoints: points,
      rpmMin,
      rpmMax,
      fieldRanges,
      interpolated,
      currentRpm: rpmMin,
      playing: false,
      pausedAtRpm: null,
      startedAtMs: null,
    });
  },

  play: () => {
    const state = get();
    if (state.sweepPoints.length < 2) return;
    if (state.playing) return;

    // If at the end, reset first
    let resumeRpm = state.pausedAtRpm ?? state.currentRpm;
    if (resumeRpm >= state.rpmMax) {
      resumeRpm = state.rpmMin;
    }

    // Compute startedAtMs such that the elapsed time maps to resumeRpm
    const rpmRange = state.rpmMax - state.rpmMin;
    const fraction = (resumeRpm - state.rpmMin) / rpmRange;
    const effectiveElapsed = fraction * PULL_DURATION_MS / state.speed;
    const now = performance.now();

    set({
      playing: true,
      startedAtMs: now - effectiveElapsed,
      pausedAtRpm: null,
      currentRpm: resumeRpm,
    });

    // Start the rAF loop
    const loop = (ts: number) => {
      const s = get();
      if (!s.playing) return;
      s.tick(ts);
      const rafId = requestAnimationFrame(loop);
      set({ _rafId: rafId });
    };
    const rafId = requestAnimationFrame(loop);
    set({ _rafId: rafId });
  },

  pause: () => {
    const state = get();
    if (state._rafId != null) {
      cancelAnimationFrame(state._rafId);
    }
    set({
      playing: false,
      pausedAtRpm: state.currentRpm,
      _rafId: null,
    });
  },

  reset: () => {
    const state = get();
    if (state._rafId != null) {
      cancelAnimationFrame(state._rafId);
    }
    const rpm = state.rpmMin;
    const interpolated =
      state.sweepPoints.length > 0
        ? interpolatePerfAtRpm(state.sweepPoints, rpm)
        : null;
    set({
      playing: false,
      currentRpm: rpm,
      pausedAtRpm: null,
      startedAtMs: null,
      interpolated,
      _rafId: null,
    });
  },

  scrubTo: (rpm: number) => {
    const state = get();
    if (state._rafId != null) {
      cancelAnimationFrame(state._rafId);
    }
    const clamped = Math.max(state.rpmMin, Math.min(state.rpmMax, rpm));
    const interpolated =
      state.sweepPoints.length > 0
        ? interpolatePerfAtRpm(state.sweepPoints, clamped)
        : null;
    set({
      playing: false,
      currentRpm: clamped,
      pausedAtRpm: clamped,
      interpolated,
      _rafId: null,
    });
  },

  setSpeed: (s: number) => {
    const state = get();
    if (state.playing) {
      // Adjust startedAtMs so current position is preserved at new speed
      const rpmRange = state.rpmMax - state.rpmMin;
      const fraction = (state.currentRpm - state.rpmMin) / rpmRange;
      const effectiveElapsed = fraction * PULL_DURATION_MS / s;
      set({
        speed: s,
        startedAtMs: performance.now() - effectiveElapsed,
      });
    } else {
      set({ speed: s });
    }
  },

  tick: (timestampMs: number) => {
    const state = get();
    if (!state.playing || state.startedAtMs == null) return;
    if (state.sweepPoints.length < 2) return;

    const elapsed = (timestampMs - state.startedAtMs) * state.speed;
    const rpmRange = state.rpmMax - state.rpmMin;
    const fraction = Math.min(elapsed / PULL_DURATION_MS, 1);
    const rpm = state.rpmMin + fraction * rpmRange;

    const interpolated = interpolatePerfAtRpm(state.sweepPoints, rpm);

    if (fraction >= 1) {
      // Reached the end — auto-pause
      if (state._rafId != null) {
        cancelAnimationFrame(state._rafId);
      }
      set({
        currentRpm: state.rpmMax,
        interpolated,
        playing: false,
        pausedAtRpm: state.rpmMax,
        _rafId: null,
      });
    } else {
      set({ currentRpm: rpm, interpolated });
    }
  },
}));
```

- [ ] **Step 2: Verify TypeScript compiles**

Run from `gui-frontend/`:
```bash
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/state/dynoStore.ts
git commit -m "feat(dyno): add interpolation logic and playback store"
```

---

### Task 2: Tab Integration

**Files:**
- Modify: `src/state/configStore.ts:104`
- Modify: `src/components/TabBar.tsx:9-12`
- Modify: `src/App.tsx:37`
- Create: `src/components/DynoView.tsx` (placeholder)

Wire up the new tab so it appears in the UI and renders a placeholder `DynoView`.

- [ ] **Step 1: Add `"dyno"` to `ActiveTab` in `configStore.ts`**

In `src/state/configStore.ts`, change line 104:

```typescript
// Before:
export type ActiveTab = "simulation" | "config";

// After:
export type ActiveTab = "simulation" | "config" | "dyno";
```

- [ ] **Step 2: Add Dyno tab entry in `TabBar.tsx`**

In `src/components/TabBar.tsx`, change the `TABS` array (lines 9-12):

```typescript
// Before:
const TABS: TabDef[] = [
  { id: "simulation", label: "Simulation", index: "01" },
  { id: "config", label: "Config", index: "02" },
];

// After:
const TABS: TabDef[] = [
  { id: "simulation", label: "Simulation", index: "01" },
  { id: "config", label: "Config", index: "02" },
  { id: "dyno", label: "Dyno", index: "03" },
];
```

- [ ] **Step 3: Create placeholder `DynoView.tsx`**

Create `src/components/DynoView.tsx`:

```tsx
/**
 * DynoView — the "Dyno" tab: animated playback of a completed sweep.
 * Placeholder while sub-components are built.
 */
export default function DynoView() {
  return (
    <main className="flex-1 overflow-auto p-3 flex flex-col gap-3">
      <div className="h-full min-h-[400px] flex items-center justify-center">
        <span className="text-[11px] font-mono text-text-muted uppercase tracking-widest">
          Dyno tab — coming soon
        </span>
      </div>
    </main>
  );
}
```

- [ ] **Step 4: Render `DynoView` in `App.tsx`**

In `src/App.tsx`, add the import and update the tab rendering:

```typescript
// Add import (after line 6):
import DynoView from "./components/DynoView";
```

Replace line 37:
```tsx
// Before:
{activeTab === "simulation" ? <SimulationView /> : <ConfigView />}

// After:
{activeTab === "simulation" && <SimulationView />}
{activeTab === "config" && <ConfigView />}
{activeTab === "dyno" && <DynoView />}
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd gui-frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/state/configStore.ts src/components/TabBar.tsx src/App.tsx src/components/DynoView.tsx
git commit -m "feat(dyno): add Dyno tab with placeholder view"
```

---

### Task 3: GaugeCard Component

**Files:**
- Create: `src/components/dyno/GaugeCard.tsx`

A single numeric readout card with label, value, unit, and range bar.

- [ ] **Step 1: Create `src/components/dyno/GaugeCard.tsx`**

```tsx
export interface GaugeCardProps {
  /** Display label, e.g. "Brake Power" */
  label: string;
  /** Current interpolated value */
  value: number;
  /** Unit suffix, e.g. "hp", "Nm", "bar" */
  unit: string;
  /** Min/max range from the full sweep — drives the range bar */
  min: number;
  max: number;
  /** Number of decimal places for the readout. Default 1. */
  precision?: number;
  /** If true, render the card at larger size (for RPM, primary gauges). */
  primary?: boolean;
}

export default function GaugeCard({
  label,
  value,
  unit,
  min,
  max,
  precision = 1,
  primary = false,
}: GaugeCardProps) {
  const range = max - min;
  const fraction = range > 0 ? Math.max(0, Math.min(1, (value - min) / range)) : 0;
  const formatted = Number.isFinite(value) ? value.toFixed(precision) : "—";

  return (
    <div
      className={[
        "flex flex-col gap-1.5 bg-surface-raised border border-border-default rounded px-3 py-2 font-ui",
        primary ? "col-span-1" : "",
      ].join(" ")}
    >
      {/* Label */}
      <span className="text-[9px] font-semibold uppercase tracking-[0.18em] text-text-muted leading-none truncate">
        {label}
      </span>

      {/* Value + unit */}
      <div className="flex items-baseline gap-1.5">
        <span
          className={[
            "font-mono tabular-nums text-text-primary leading-none",
            primary ? "text-2xl" : "text-lg",
          ].join(" ")}
        >
          {formatted}
        </span>
        <span className="text-[10px] font-mono text-text-muted leading-none">
          {unit}
        </span>
      </div>

      {/* Range bar */}
      <div className="h-0.5 w-full bg-border-default rounded-full overflow-hidden">
        <div
          className="h-full bg-accent rounded-full transition-all duration-75"
          style={{ width: `${fraction * 100}%` }}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd gui-frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/components/dyno/GaugeCard.tsx
git commit -m "feat(dyno): add GaugeCard component"
```

---

### Task 4: GaugePanel Component

**Files:**
- Create: `src/components/dyno/GaugePanel.tsx`

The responsive grid of all gauge cards, reading from `dynoStore`.

- [ ] **Step 1: Create `src/components/dyno/GaugePanel.tsx`**

```tsx
import { useDynoStore } from "../../state/dynoStore";
import GaugeCard from "./GaugeCard";

/** Gauge definition for declarative layout. */
interface GaugeDef {
  field: string;
  label: string;
  unit: string;
  precision: number;
  /** Scale factor applied to the raw value before display. */
  scale?: number;
}

const PRIMARY_GAUGES: GaugeDef[] = [
  { field: "rpm", label: "RPM", unit: "RPM", precision: 0 },
  { field: "brake_power_hp", label: "Brake Power", unit: "hp", precision: 1 },
  { field: "brake_torque_Nm", label: "Brake Torque", unit: "Nm", precision: 1 },
];

const INDICATED_WHEEL_GAUGES: GaugeDef[] = [
  { field: "indicated_power_hp", label: "Indicated Power", unit: "hp", precision: 1 },
  { field: "indicated_torque_Nm", label: "Indicated Torque", unit: "Nm", precision: 1 },
  { field: "wheel_power_hp", label: "Wheel Power", unit: "hp", precision: 1 },
  { field: "wheel_torque_Nm", label: "Wheel Torque", unit: "Nm", precision: 1 },
];

const EFFICIENCY_GAUGES: GaugeDef[] = [
  { field: "volumetric_efficiency_atm", label: "VE (Atm)", unit: "%", precision: 1, scale: 100 },
  { field: "volumetric_efficiency_plenum", label: "VE (Plenum)", unit: "%", precision: 1, scale: 100 },
  { field: "drivetrain_efficiency", label: "Drivetrain Eff.", unit: "%", precision: 1, scale: 100 },
];

const MEP_GAUGES: GaugeDef[] = [
  { field: "imep_bar", label: "IMEP", unit: "bar", precision: 2 },
  { field: "bmep_bar", label: "BMEP", unit: "bar", precision: 2 },
  { field: "fmep_bar", label: "FMEP", unit: "bar", precision: 2 },
];

const INTAKE_GAUGES: GaugeDef[] = [
  { field: "plenum_pressure_bar", label: "Plenum Pressure", unit: "bar", precision: 3 },
  { field: "restrictor_mdot", label: "Restrictor Flow", unit: "g/s", precision: 2, scale: 1000 },
  { field: "intake_mass_per_cycle_g", label: "Intake Mass/Cycle", unit: "g", precision: 3 },
];

/** Render a row of gauge cards from a gauge definition array. */
function GaugeRow({
  gauges,
  primary = false,
}: {
  gauges: GaugeDef[];
  primary?: boolean;
}) {
  const interpolated = useDynoStore((s) => s.interpolated);
  const fieldRanges = useDynoStore((s) => s.fieldRanges);

  return (
    <>
      {gauges.map((g) => {
        const raw = interpolated?.[g.field as keyof typeof interpolated];
        const rawNum = typeof raw === "number" ? raw : 0;
        const scale = g.scale ?? 1;
        const value = rawNum * scale;
        const range = fieldRanges[g.field];
        const min = (range?.min ?? 0) * scale;
        const max = (range?.max ?? 0) * scale;

        return (
          <GaugeCard
            key={g.field}
            label={g.label}
            value={value}
            unit={g.unit}
            min={min}
            max={max}
            precision={g.precision}
            primary={primary}
          />
        );
      })}
    </>
  );
}

export default function GaugePanel() {
  const interpolated = useDynoStore((s) => s.interpolated);

  if (!interpolated) return null;

  const choked = interpolated.restrictor_choked ?? false;

  return (
    <div className="flex flex-col gap-2">
      {/* Primary row — 3 large gauges */}
      <div className="grid grid-cols-3 gap-2">
        <GaugeRow gauges={PRIMARY_GAUGES} primary />
      </div>

      {/* Indicated & Wheel — 4 gauges */}
      <div className="grid grid-cols-4 gap-2">
        <GaugeRow gauges={INDICATED_WHEEL_GAUGES} />
      </div>

      {/* Efficiency — 3 gauges */}
      <div className="grid grid-cols-3 gap-2">
        <GaugeRow gauges={EFFICIENCY_GAUGES} />
      </div>

      {/* MEP — 3 gauges */}
      <div className="grid grid-cols-3 gap-2">
        <GaugeRow gauges={MEP_GAUGES} />
      </div>

      {/* Intake — 3 gauges + choked indicator */}
      <div className="grid grid-cols-4 gap-2">
        <GaugeRow gauges={INTAKE_GAUGES} />

        {/* Choked indicator */}
        <div className="flex flex-col items-center justify-center gap-1.5 bg-surface-raised border border-border-default rounded px-3 py-2 font-ui">
          <span className="text-[9px] font-semibold uppercase tracking-[0.18em] text-text-muted leading-none">
            Restrictor
          </span>
          <div className="flex items-center gap-2">
            <span
              className={[
                "inline-block w-2 h-2 rounded-full transition-colors duration-150",
                choked ? "bg-accent" : "bg-text-muted opacity-40",
              ].join(" ")}
            />
            <span
              className={[
                "text-[10px] font-mono font-semibold uppercase tracking-[0.14em] leading-none",
                choked ? "text-accent" : "text-text-muted",
              ].join(" ")}
            >
              {choked ? "Choked" : "Unchoked"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd gui-frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/components/dyno/GaugePanel.tsx
git commit -m "feat(dyno): add GaugePanel with all parameter readouts"
```

---

### Task 5: TransportBar Component

**Files:**
- Create: `src/components/dyno/TransportBar.tsx`

Play/pause/reset, scrub slider, speed selector, RPM readout.

- [ ] **Step 1: Create `src/components/dyno/TransportBar.tsx`**

```tsx
import { Play, Pause, RotateCcw } from "lucide-react";
import { useDynoStore } from "../../state/dynoStore";

const SPEEDS = [0.5, 1, 2];

export default function TransportBar() {
  const playing = useDynoStore((s) => s.playing);
  const currentRpm = useDynoStore((s) => s.currentRpm);
  const rpmMin = useDynoStore((s) => s.rpmMin);
  const rpmMax = useDynoStore((s) => s.rpmMax);
  const speed = useDynoStore((s) => s.speed);
  const play = useDynoStore((s) => s.play);
  const pause = useDynoStore((s) => s.pause);
  const reset = useDynoStore((s) => s.reset);
  const scrubTo = useDynoStore((s) => s.scrubTo);
  const setSpeed = useDynoStore((s) => s.setSpeed);

  const hasData = rpmMax > rpmMin;

  return (
    <div className="h-10 flex items-center gap-3 px-3 bg-surface border-b border-border-default font-ui">
      {/* Play / Pause */}
      <button
        type="button"
        onClick={() => (playing ? pause() : play())}
        disabled={!hasData}
        className={[
          "flex items-center justify-center w-7 h-7 rounded",
          "transition-colors duration-100",
          hasData
            ? "text-accent hover:bg-surface-raised"
            : "text-text-muted opacity-40 cursor-not-allowed",
        ].join(" ")}
        aria-label={playing ? "Pause" : "Play"}
      >
        {playing ? <Pause size={14} /> : <Play size={14} />}
      </button>

      {/* Reset */}
      <button
        type="button"
        onClick={reset}
        disabled={!hasData}
        className={[
          "flex items-center justify-center w-7 h-7 rounded",
          "transition-colors duration-100",
          hasData
            ? "text-text-secondary hover:text-text-primary hover:bg-surface-raised"
            : "text-text-muted opacity-40 cursor-not-allowed",
        ].join(" ")}
        aria-label="Reset"
      >
        <RotateCcw size={14} />
      </button>

      {/* Scrub slider */}
      <input
        type="range"
        min={rpmMin}
        max={rpmMax}
        step={1}
        value={currentRpm}
        onChange={(e) => scrubTo(Number(e.target.value))}
        disabled={!hasData}
        className="flex-1 h-1 accent-accent cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
        aria-label="Scrub RPM"
      />

      {/* RPM readout */}
      <span className="text-[11px] font-mono tabular-nums text-text-secondary leading-none min-w-[4.5rem] text-right">
        {hasData ? `${Math.round(currentRpm)} RPM` : "— RPM"}
      </span>

      {/* Divider */}
      <div className="w-px h-5 bg-border-default" aria-hidden />

      {/* Speed buttons */}
      <div className="flex items-center gap-1">
        {SPEEDS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSpeed(s)}
            disabled={!hasData}
            className={[
              "px-2 py-1 rounded text-[10px] font-mono font-medium leading-none",
              "transition-colors duration-100",
              s === speed
                ? "bg-accent text-white"
                : hasData
                  ? "text-text-muted hover:text-text-primary hover:bg-surface-raised"
                  : "text-text-muted opacity-40 cursor-not-allowed",
            ].join(" ")}
          >
            {s}x
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd gui-frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/components/dyno/TransportBar.tsx
git commit -m "feat(dyno): add TransportBar with play/pause/scrub/speed"
```

---

### Task 6: ProgressiveCharts Component

**Files:**
- Create: `src/components/dyno/ProgressiveCharts.tsx`

Six charts that draw progressively as RPM advances, with a vertical playhead.

- [ ] **Step 1: Create `src/components/dyno/ProgressiveCharts.tsx`**

```tsx
import { useMemo } from "react";
import { useDynoStore } from "../../state/dynoStore";
import LineChart, { type SeriesDef, type ChartRow } from "../charts/LineChart";
import type { PerfDict } from "../../types/events";

/* ========================================================================= */
/* Chart definitions — same series as SweepCurves for visual parity          */
/* ========================================================================= */

interface ChartDef {
  ordinal: string;
  title: string;
  yLabel: string;
  series: SeriesDef[];
  /** If true, compute choked ranges for this chart. */
  choked?: boolean;
}

const CHARTS: ChartDef[] = [
  {
    ordinal: "01",
    title: "Power · HP",
    yLabel: "Power · hp",
    series: [
      { key: "indicated_power_hp", label: "Indicated", color: "#E5484D" },
      { key: "brake_power_hp", label: "Brake", color: "#4493F8" },
      { key: "wheel_power_hp", label: "Wheel", color: "#4493F8", dashed: true },
    ],
  },
  {
    ordinal: "02",
    title: "Torque · Nm",
    yLabel: "Torque · Nm",
    series: [
      { key: "indicated_torque_Nm", label: "Indicated", color: "#E5484D" },
      { key: "brake_torque_Nm", label: "Brake", color: "#4493F8" },
      { key: "wheel_torque_Nm", label: "Wheel", color: "#4493F8", dashed: true },
    ],
  },
  {
    ordinal: "03",
    title: "Volumetric Eff · %",
    yLabel: "VE · %",
    series: [
      { key: "ve_atm_pct", label: "Atmospheric", color: "#3DD68C" },
      { key: "ve_plenum_pct", label: "Plenum", color: "#3DD68C", dashed: true },
    ],
  },
  {
    ordinal: "04",
    title: "IMEP · BMEP · FMEP · bar",
    yLabel: "MEP · bar",
    series: [
      { key: "imep_bar", label: "IMEP", color: "#E8A34A" },
      { key: "bmep_bar", label: "BMEP", color: "#E8A34A", dashed: true },
      { key: "fmep_bar", label: "FMEP", color: "#E8A34A", dashed: true },
    ],
  },
  {
    ordinal: "05",
    title: "Plenum Pressure · bar",
    yLabel: "P · bar",
    series: [
      { key: "plenum_pressure_bar", label: "Plenum", color: "#6BC5D8" },
    ],
  },
  {
    ordinal: "06",
    title: "Restrictor · g/s",
    yLabel: "ṁ · g/s",
    series: [
      { key: "restrictor_mdot_gs", label: "Mass Flow", color: "#C586E8" },
    ],
    choked: true,
  },
];

/* ========================================================================= */
/* Helpers                                                                   */
/* ========================================================================= */

/** Extend a PerfDict with pre-scaled fields matching SweepCurves conventions. */
interface PerfRow extends ChartRow {
  rpm: number;
  ve_atm_pct: number;
  ve_plenum_pct: number;
  restrictor_mdot_gs: number;
}

function toPerfRow(p: PerfDict): PerfRow {
  return {
    ...p,
    ve_atm_pct: (p.volumetric_efficiency_atm ?? 0) * 100,
    ve_plenum_pct: (p.volumetric_efficiency_plenum ?? 0) * 100,
    restrictor_mdot_gs: (p.restrictor_mdot ?? 0) * 1000,
  } as PerfRow;
}

/** Compute contiguous choked RPM ranges from an array of PerfDicts. */
function computeChokedRanges(rows: PerfRow[]): Array<[number, number]> {
  const ranges: Array<[number, number]> = [];
  let start: number | null = null;
  let last: number | null = null;
  for (const row of rows) {
    if (row.restrictor_choked) {
      if (start == null) start = row.rpm;
      last = row.rpm;
    } else {
      if (start != null && last != null) ranges.push([start, last]);
      start = null;
      last = null;
    }
  }
  if (start != null && last != null) ranges.push([start, last]);
  return ranges;
}

/* ========================================================================= */
/* ProgressiveCharts                                                         */
/* ========================================================================= */

export default function ProgressiveCharts() {
  const sweepPoints = useDynoStore((s) => s.sweepPoints);
  const currentRpm = useDynoStore((s) => s.currentRpm);
  const interpolated = useDynoStore((s) => s.interpolated);
  const rpmMin = useDynoStore((s) => s.rpmMin);
  const rpmMax = useDynoStore((s) => s.rpmMax);
  const playing = useDynoStore((s) => s.playing);

  /**
   * Build the visible rows: all sweep points up to currentRpm,
   * plus an interpolated point at the playhead for smooth extension.
   */
  const { visibleRows, allRows } = useMemo(() => {
    const all = sweepPoints.map(toPerfRow);
    if (all.length === 0 || !interpolated) return { visibleRows: [], allRows: all };

    // Points that have been "passed"
    const passed = all.filter((r) => r.rpm <= currentRpm);

    // Add the interpolated point at the playhead if it's between data points
    const lastPassedRpm = passed.length > 0 ? passed[passed.length - 1].rpm : -1;
    if (currentRpm > lastPassedRpm && currentRpm < rpmMax) {
      passed.push(toPerfRow(interpolated));
    }

    // If we're at or past the end, show all points
    if (currentRpm >= rpmMax) {
      return { visibleRows: all, allRows: all };
    }

    return { visibleRows: passed, allRows: all };
  }, [sweepPoints, currentRpm, interpolated, rpmMax]);

  /** The playhead RPM — show it only while not at the very end. */
  const playheadRpm =
    visibleRows.length > 0 && currentRpm < rpmMax ? currentRpm : null;

  /** Choked ranges computed from visible rows only (for progressive reveal). */
  const chokedRanges = useMemo(
    () => computeChokedRanges(visibleRows as PerfRow[]),
    [visibleRows],
  );

  if (allRows.length === 0) {
    return (
      <div className="h-[300px] flex items-center justify-center">
        <span className="text-[11px] font-mono text-text-muted uppercase tracking-widest">
          No sweep data available
        </span>
      </div>
    );
  }

  // Use the full RPM range for consistent x-axis domain across all states
  const xDomain: [number, number] = [rpmMin, rpmMax];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-2">
      {CHARTS.map((chart) => (
        <section
          key={chart.ordinal}
          className="flex flex-col bg-surface-raised border border-border-emphasis rounded font-ui"
          aria-label={chart.title}
        >
          {/* Header strip — mirrors SweepCurves ChartPanel */}
          <header className="flex items-stretch border-b border-border-default">
            <div className="flex-1 flex items-baseline gap-2 px-3 py-2 min-w-0">
              <span className="text-[9px] font-mono text-text-muted leading-none tabular-nums">
                [{chart.ordinal}]
              </span>
              <h3 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-text-primary leading-none truncate">
                {chart.title}
              </h3>
            </div>
          </header>

          {/* Chart body */}
          <div className="p-3">
            <LineChart
              data={visibleRows}
              xKey="rpm"
              series={chart.series}
              yLabel={chart.yLabel}
              selectedRpm={playheadRpm}
              chokedRanges={chart.choked ? chokedRanges : undefined}
              xDomain={xDomain}
            />
          </div>
        </section>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Check if `LineChart` supports `xDomain` prop**

Read `src/components/charts/LineChart.tsx` to verify if `xDomain` is accepted. If it's not currently a prop, we need to add it so the x-axis range stays fixed during progressive drawing. Check the `LineChartProps` interface and the `XAxis` component usage.

If `xDomain` is not supported, add it:

In `src/components/charts/LineChart.tsx`, add to the `LineChartProps` interface:

```typescript
/** Fixed x-axis domain [min, max]. If omitted, Recharts auto-scales. */
xDomain?: [number, number];
```

Add `xDomain` to the destructured props:

```typescript
export default function LineChart({
  data,
  xKey,
  series,
  yLabel,
  height = 200,
  selectedRpm = null,
  onPointClick,
  chokedRanges,
  showDots = true,
  xDomain,    // <-- add this
}: LineChartProps) {
```

Then on the `<XAxis>` component, add the `domain` prop:

```tsx
<XAxis
  // ... existing props ...
  domain={xDomain ?? ["dataMin", "dataMax"]}
/>
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd gui-frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add src/components/dyno/ProgressiveCharts.tsx src/components/charts/LineChart.tsx
git commit -m "feat(dyno): add ProgressiveCharts with playhead and progressive drawing"
```

---

### Task 7: Wire Up DynoView

**Files:**
- Modify: `src/components/DynoView.tsx`

Replace the placeholder with the real composition of GaugePanel, TransportBar, ProgressiveCharts, and the store lifecycle hook.

- [ ] **Step 1: Replace `DynoView.tsx` with full implementation**

```tsx
import { useEffect } from "react";
import { useDynoStore } from "../state/dynoStore";
import { useSweepStore } from "../state/sweepStore";
import GaugePanel from "./dyno/GaugePanel";
import TransportBar from "./dyno/TransportBar";
import ProgressiveCharts from "./dyno/ProgressiveCharts";

/**
 * DynoView — the "Dyno" tab: animated playback of a completed sweep.
 *
 * Reads from sweepStore, loads data into dynoStore on mount and when
 * the sweep changes. Sub-components read from dynoStore.
 */
export default function DynoView() {
  const sweep = useSweepStore((s) => s.sweep);
  const loadSweepData = useDynoStore((s) => s.loadSweepData);
  const sweepPoints = useDynoStore((s) => s.sweepPoints);

  // Load/reload sweep data when the sweep changes
  useEffect(() => {
    loadSweepData();
  }, [sweep, loadSweepData]);

  const hasSweep = sweepPoints.length > 0;

  return (
    <main className="flex-1 overflow-auto flex flex-col">
      {hasSweep ? (
        <>
          <div className="p-3 pb-0">
            <GaugePanel />
          </div>
          <TransportBar />
          <div className="flex-1 p-3 overflow-auto">
            <ProgressiveCharts />
          </div>
        </>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col items-center gap-3">
            <div className="flex items-center gap-2">
              <span
                className="inline-block w-1.5 h-1.5 rounded-full bg-text-muted"
                aria-hidden
              />
              <span className="text-[10px] font-ui font-semibold uppercase tracking-[0.22em] text-text-muted leading-none">
                No Sweep Data
              </span>
            </div>
            <div className="w-16 h-px bg-border-default" aria-hidden />
            <p className="text-[11px] font-mono text-text-secondary leading-none text-center">
              Load a sweep from the Simulation tab to use Dyno playback
            </p>
          </div>
        </div>
      )}
    </main>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd gui-frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/components/DynoView.tsx
git commit -m "feat(dyno): wire up DynoView with gauges, transport, and charts"
```

---

### Task 8: Manual Smoke Test & Polish

**Files:**
- Potentially modify any of the above files based on findings

Verify the feature works end-to-end in the browser.

- [ ] **Step 1: Start the dev servers**

In one terminal, start the backend:
```bash
cd /Users/nmurray/Developer/1d && python -m engine_simulator.gui
```

In another terminal, start the frontend:
```bash
cd /Users/nmurray/Developer/1d/gui-frontend && npm run dev
```

- [ ] **Step 2: Open the app and verify tab appears**

Open `http://localhost:5173`. Verify:
- Three tabs visible: Simulation, Config, Dyno
- Clicking Dyno shows the "No Sweep Data" empty state if no sweep is loaded

- [ ] **Step 3: Load a sweep and verify Dyno populates**

Either run a new sweep or load an existing one from the sweep list sidebar. Switch to the Dyno tab and verify:
- Gauge panel appears with all parameter cards
- Transport bar is visible with play/pause/reset/scrub/speed
- Charts show below with the full RPM range on x-axis

- [ ] **Step 4: Test playback**

Click Play. Verify:
- RPM advances smoothly
- Gauge values update in real-time
- Chart lines draw in progressively from left to right
- Playhead (vertical line) moves across charts
- Auto-pauses at end of RPM range

- [ ] **Step 5: Test transport controls**

- Pause during playback — verify it freezes
- Play again — verify it resumes from paused position
- Drag scrub slider — verify it pauses and jumps to position
- Click Reset — verify it returns to start
- Change speed to 0.5x and 2x — verify playback speed changes

- [ ] **Step 6: Fix any issues found**

Address any visual, behavioral, or TypeScript issues discovered during testing.

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "feat(dyno): complete Dyno playback tab"
```
