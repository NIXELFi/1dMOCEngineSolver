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
