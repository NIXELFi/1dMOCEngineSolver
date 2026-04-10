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
    // Cancel any running animation before resetting state
    const prev = get();
    if (prev._rafId != null) {
      cancelAnimationFrame(prev._rafId);
    }

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
        _rafId: null,
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
        _rafId: null,
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
      if (!get().playing) return; // tick may have auto-paused
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
