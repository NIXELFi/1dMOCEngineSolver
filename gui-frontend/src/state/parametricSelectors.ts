/**
 * Pure derived-data functions for the parametric tab.
 *
 * These are NOT stored in state. They take study data + UI controls
 * (objective, RPM window) and return computed views. This lets the
 * user change the objective and have the ranking re-compute instantly
 * without re-fetching anything.
 */

import type {
  ComparisonRow,
  LiveParametricStudy,
  ObjectiveKey,
  ParametricRun,
  PerfDict,
  RunMetrics,
} from "../types/parametric";

const EPSILON = 1e-9;

function getNum(perf: PerfDict, key: string): number | null {
  const v = perf[key];
  if (typeof v !== "number") return null;
  if (!Number.isFinite(v)) return null;
  return v;
}

function peakOf(
  run: ParametricRun,
  key: string,
): { value: number; rpm: number } | null {
  let best: { value: number; rpm: number } | null = null;
  for (const perf of run.sweep_results) {
    const v = getNum(perf, key);
    if (v === null) continue;
    if (best === null || v > best.value) {
      best = { value: v, rpm: perf.rpm };
    }
  }
  return best;
}

function interpolate(
  run: ParametricRun,
  key: string,
  targetRpm: number,
): number | null {
  const results = run.sweep_results.filter(
    (p) => getNum(p, key) !== null,
  );
  if (results.length === 0) return null;
  if (results.length === 1) {
    return getNum(results[0], key);
  }
  // results are already sorted by RPM (store guarantees it)
  if (targetRpm <= results[0].rpm) return getNum(results[0], key);
  if (targetRpm >= results[results.length - 1].rpm) {
    return getNum(results[results.length - 1], key);
  }
  for (let i = 0; i < results.length - 1; i++) {
    const a = results[i];
    const b = results[i + 1];
    if (targetRpm >= a.rpm && targetRpm <= b.rpm) {
      const aVal = getNum(a, key)!;
      const bVal = getNum(b, key)!;
      const t = (targetRpm - a.rpm) / (b.rpm - a.rpm + EPSILON);
      return aVal + t * (bVal - aVal);
    }
  }
  return null;
}

function torqueAreaOver(
  run: ParametricRun,
  window: [number, number],
): number | null {
  const [lo, hi] = window;
  // Use trapezoidal integration over the points inside the window
  const points = run.sweep_results
    .filter((p) => p.rpm >= lo && p.rpm <= hi)
    .slice()
    .sort((a, b) => a.rpm - b.rpm);
  if (points.length < 2) return null;

  let area = 0;
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i];
    const b = points[i + 1];
    const aT = getNum(a, "brake_torque_Nm");
    const bT = getNum(b, "brake_torque_Nm");
    if (aT === null || bT === null) continue;
    area += ((aT + bT) / 2) * (b.rpm - a.rpm);
  }
  return area;
}

function avgVe(run: ParametricRun): number | null {
  const values = run.sweep_results
    .map((p) => getNum(p, "volumetric_efficiency_atm"))
    .filter((v): v is number => v !== null);
  if (values.length === 0) return null;
  return values.reduce((s, v) => s + v, 0) / values.length;
}

export function computeRunMetrics(
  run: ParametricRun,
  objectiveRpm: number,
  objectiveRpmWindow: [number, number],
): RunMetrics {
  const peakPower = peakOf(run, "brake_power_hp");
  const peakTorque = peakOf(run, "brake_torque_Nm");
  const peakVe = peakOf(run, "volumetric_efficiency_atm");

  return {
    peak_power_hp: peakPower?.value ?? null,
    peak_power_rpm: peakPower?.rpm ?? null,
    peak_torque_Nm: peakTorque?.value ?? null,
    peak_torque_rpm: peakTorque?.rpm ?? null,
    torque_area: torqueAreaOver(run, objectiveRpmWindow),
    power_at_rpm: interpolate(run, "brake_power_hp", objectiveRpm),
    torque_at_rpm: interpolate(run, "brake_torque_Nm", objectiveRpm),
    ve_peak: peakVe?.value ?? null,
    ve_avg: avgVe(run),
  };
}

function metricForObjective(
  metrics: RunMetrics,
  objective: ObjectiveKey,
): number | null {
  switch (objective) {
    case "peak_power":
      return metrics.peak_power_hp;
    case "peak_torque":
      return metrics.peak_torque_Nm;
    case "torque_area":
      return metrics.torque_area;
    case "power_at_rpm":
      return metrics.power_at_rpm;
    case "torque_at_rpm":
      return metrics.torque_at_rpm;
  }
}

export function computeComparisonTable(
  study: LiveParametricStudy,
  objective: ObjectiveKey,
  objectiveRpm: number,
  objectiveRpmWindow: [number, number],
): ComparisonRow[] {
  const rows: ComparisonRow[] = study.runs.map((run, index) => ({
    index,
    parameter_value: run.parameter_value,
    metrics: computeRunMetrics(run, objectiveRpm, objectiveRpmWindow),
    status: run.status,
    rank: null,
    isBest: false,
    error: run.error,
  }));

  // Rank only successful runs by the selected objective (descending).
  const ranked = rows
    .filter((r) => r.status === "done")
    .map((r) => ({
      row: r,
      score: metricForObjective(r.metrics, objective),
    }))
    .filter((entry): entry is { row: ComparisonRow; score: number } =>
      entry.score !== null && Number.isFinite(entry.score),
    )
    .sort((a, b) => b.score - a.score);

  ranked.forEach((entry, i) => {
    entry.row.rank = i + 1;
    if (i === 0) entry.row.isBest = true;
  });

  // Return: ranked successes first, then errored runs at the bottom
  return [
    ...ranked.map((e) => e.row),
    ...rows.filter((r) => r.status !== "done" || r.rank === null),
  ];
}

export interface HeatmapData {
  parameterValues: number[];
  rpms: number[];
  values: (number | null)[][]; // [parameter_value_index][rpm_index]
  metricKey: string;
}

export function computeHeatmapData(
  study: LiveParametricStudy,
  metricKey: string,
): HeatmapData {
  // Collect the union of RPMs across all runs, sorted
  const rpmSet = new Set<number>();
  for (const run of study.runs) {
    for (const perf of run.sweep_results) {
      rpmSet.add(perf.rpm);
    }
  }
  const rpms = Array.from(rpmSet).sort((a, b) => a - b);

  // Sort by parameter value ascending
  const sortedRuns = study.runs
    .map((r, idx) => ({ run: r, idx }))
    .sort((a, b) => a.run.parameter_value - b.run.parameter_value);

  const parameterValues = sortedRuns.map((e) => e.run.parameter_value);

  const values: (number | null)[][] = sortedRuns.map(({ run }) => {
    return rpms.map((rpm) => {
      const perf = run.sweep_results.find((p) => p.rpm === rpm);
      if (!perf) return null;
      return getNum(perf, metricKey);
    });
  });

  return { parameterValues, rpms, values, metricKey };
}
