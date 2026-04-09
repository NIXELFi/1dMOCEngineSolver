import { useMemo } from "react";
import { useSweepStore } from "../state/sweepStore";
import type { PerfDict } from "../types/events";
import LineChart, { type SeriesDef } from "./charts/LineChart";

/* ========================================================================= */
/* Types                                                                     */
/* ========================================================================= */

/**
 * One row of plottable data: a flattened PerfDict plus three derived,
 * pre-scaled fields (ve_atm_pct, ve_plenum_pct, restrictor_mdot_gs) so the
 * charts receive the same units they display.
 *
 * Shape is structurally compatible with LineChart's ChartRow via the index
 * signature below.
 */
interface PerfRow extends PerfDict {
  ve_atm_pct: number;
  ve_plenum_pct: number;
  restrictor_mdot_gs: number;
  /** index signature — lets PerfRow satisfy ChartRow without a cast */
  [extraKey: string]: number | boolean | undefined;
}

/* ========================================================================= */
/* SweepCurves — the 6-chart headline grid                                   */
/* ========================================================================= */

/**
 * SweepCurves — the headline 6-chart grid of the live monitor.
 *
 * Charts (per §5 of the design spec):
 *   01  Power         → indicated / brake / wheel  [hp]
 *   02  Torque        → indicated / brake / wheel  [Nm]
 *   03  VE            → atm / plenum               [%]
 *   04  IMEP · BMEP   → mean effective pressure    [bar]
 *   05  Plenum        → intake plenum pressure     [bar]
 *   06  Restrictor    → air mass flow              [g/s]  + choked band
 *
 * Clicking any data point on any chart sets the globally-selected RPM; a
 * vertical accent marker then appears on every chart at that x value.
 */
export default function SweepCurves() {
  const sweep = useSweepStore((s) => s.sweep);
  const selectedRpm = useSweepStore((s) => s.selectedRpm);
  const setSelectedRpm = useSweepStore((s) => s.setSelectedRpm);

  /* ---- Derive plottable rows from the sweep snapshot ------------------- */
  const rows = useMemo<PerfRow[]>(() => {
    if (!sweep) return [];
    const out: PerfRow[] = [];
    for (const r of Object.values(sweep.rpms)) {
      if (r.status === "done" && r.perf) {
        const p = r.perf;
        out.push({
          ...p,
          ve_atm_pct: (p.volumetric_efficiency_atm ?? 0) * 100,
          ve_plenum_pct: (p.volumetric_efficiency_plenum ?? 0) * 100,
          restrictor_mdot_gs: (p.restrictor_mdot ?? 0) * 1000,
        });
      }
    }
    out.sort((a, b) => a.rpm - b.rpm);
    return out;
  }, [sweep]);

  /* ---- Compute contiguous choked ranges for the restrictor chart ------- */
  const chokedRanges = useMemo<Array<[number, number]>>(() => {
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
  }, [rows]);

  /* ---- Handle empty / pre-data states ---------------------------------- */
  if (rows.length === 0) {
    const message =
      sweep && (sweep.status === "running" || sweep.status === "idle")
        ? "Awaiting first completed RPM…"
        : "Click Run Sweep to start a new sweep";
    return <EmptyState message={message} />;
  }

  /* ---- Series definitions (kept close to the panels for readability) --- */
  const powerSeries: SeriesDef[] = [
    { key: "indicated_power_hp", label: "Indicated", color: "#E5484D" },
    { key: "brake_power_hp", label: "Brake", color: "#4493F8" },
    { key: "wheel_power_hp", label: "Wheel", color: "#4493F8", dashed: true },
  ];

  const torqueSeries: SeriesDef[] = [
    { key: "indicated_torque_Nm", label: "Indicated", color: "#E5484D" },
    { key: "brake_torque_Nm", label: "Brake", color: "#4493F8" },
    { key: "wheel_torque_Nm", label: "Wheel", color: "#4493F8", dashed: true },
  ];

  const veSeries: SeriesDef[] = [
    { key: "ve_atm_pct", label: "Atmospheric", color: "#3DD68C" },
    { key: "ve_plenum_pct", label: "Plenum", color: "#3DD68C", dashed: true },
  ];

  const mepSeries: SeriesDef[] = [
    { key: "imep_bar", label: "IMEP", color: "#E8A34A" },
    { key: "bmep_bar", label: "BMEP", color: "#E8A34A", dashed: true },
  ];

  const plenumSeries: SeriesDef[] = [
    { key: "plenum_pressure_bar", label: "Plenum", color: "#6BC5D8" },
  ];

  const restrictorSeries: SeriesDef[] = [
    { key: "restrictor_mdot_gs", label: "Mass Flow", color: "#C586E8" },
  ];

  /* ---- Render the 6-chart grid ----------------------------------------- */
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-2">
      <ChartPanel
        ordinal="01"
        title="Power · HP"
        nPoints={rows.length}
      >
        <LineChart
          data={rows}
          xKey="rpm"
          series={powerSeries}
          yLabel="Power · hp"
          selectedRpm={selectedRpm}
          onPointClick={setSelectedRpm}
        />
      </ChartPanel>

      <ChartPanel
        ordinal="02"
        title="Torque · Nm"
        nPoints={rows.length}
      >
        <LineChart
          data={rows}
          xKey="rpm"
          series={torqueSeries}
          yLabel="Torque · Nm"
          selectedRpm={selectedRpm}
          onPointClick={setSelectedRpm}
        />
      </ChartPanel>

      <ChartPanel
        ordinal="03"
        title="Volumetric Eff · %"
        nPoints={rows.length}
      >
        <LineChart
          data={rows}
          xKey="rpm"
          series={veSeries}
          yLabel="VE · %"
          selectedRpm={selectedRpm}
          onPointClick={setSelectedRpm}
        />
      </ChartPanel>

      <ChartPanel
        ordinal="04"
        title="IMEP · BMEP · bar"
        nPoints={rows.length}
      >
        <LineChart
          data={rows}
          xKey="rpm"
          series={mepSeries}
          yLabel="MEP · bar"
          selectedRpm={selectedRpm}
          onPointClick={setSelectedRpm}
        />
      </ChartPanel>

      <ChartPanel
        ordinal="05"
        title="Plenum Pressure · bar"
        nPoints={rows.length}
      >
        <LineChart
          data={rows}
          xKey="rpm"
          series={plenumSeries}
          yLabel="P · bar"
          selectedRpm={selectedRpm}
          onPointClick={setSelectedRpm}
        />
      </ChartPanel>

      <ChartPanel
        ordinal="06"
        title="Restrictor · g/s"
        nPoints={rows.length}
        chokedActive={chokedRanges.length > 0}
      >
        <LineChart
          data={rows}
          xKey="rpm"
          series={restrictorSeries}
          yLabel="ṁ · g/s"
          selectedRpm={selectedRpm}
          onPointClick={setSelectedRpm}
          chokedRanges={chokedRanges}
        />
      </ChartPanel>
    </div>
  );
}

/* ========================================================================= */
/* ChartPanel — the bordered panel chrome with header strip                  */
/* ========================================================================= */

function ChartPanel({
  ordinal,
  title,
  nPoints,
  chokedActive,
  children,
}: {
  ordinal: string;
  title: string;
  nPoints: number;
  chokedActive?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section
      className="flex flex-col bg-surface-raised border border-border-emphasis rounded font-ui"
      aria-label={title}
    >
      {/* Header strip */}
      <header className="flex items-stretch border-b border-border-default">
        <div className="flex-1 flex items-baseline gap-2 px-3 py-2 min-w-0">
          <span className="text-[9px] font-mono text-text-muted leading-none tabular-nums">
            [{ordinal}]
          </span>
          <h3 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-text-primary leading-none truncate">
            {title}
          </h3>
        </div>

        {/* Right side: optional choked indicator, then n = count */}
        <div className="flex items-center">
          {chokedActive && (
            <div className="flex items-center gap-1.5 px-2.5 border-l border-border-default">
              <span
                className="inline-block w-1 h-1 rounded-full bg-accent"
                aria-hidden
              />
              <span className="text-[9px] font-mono font-semibold uppercase tracking-[0.14em] text-accent leading-none">
                Choked
              </span>
            </div>
          )}
          <div className="flex items-center gap-1 px-3 border-l border-border-default">
            <span className="text-[9px] font-mono uppercase tracking-[0.14em] text-text-muted leading-none">
              n
            </span>
            <span className="text-[9px] font-mono text-text-muted leading-none">
              =
            </span>
            <span className="text-[9px] font-mono tabular-nums text-text-secondary leading-none">
              {String(nPoints).padStart(2, "0")}
            </span>
          </div>
        </div>
      </header>

      {/* Chart body */}
      <div className="p-3">{children}</div>
    </section>
  );
}

/* ========================================================================= */
/* EmptyState — the instrument-chassis placeholder                           */
/* ========================================================================= */

function EmptyState({ message }: { message: string }) {
  return (
    <div className="h-full min-h-[400px] flex items-center justify-center">
      {/* Outer wrapper hosts the bracketed corner marks */}
      <div className="relative">
        <CornerBrackets />

        <div className="relative bg-surface border border-border-default rounded font-ui">
          <div className="flex flex-col items-center gap-3 px-10 py-8">
            {/* Status label row */}
            <div className="flex items-center gap-2">
              <span
                className="inline-block w-1.5 h-1.5 rounded-full bg-text-muted"
                aria-hidden
              />
              <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-text-muted leading-none">
                No Sweep Data
              </span>
            </div>

            {/* Hairline divider */}
            <div className="w-16 h-px bg-border-default" aria-hidden />

            {/* Message */}
            <p className="text-[11px] font-mono text-text-secondary leading-none text-center">
              {message}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ========================================================================= */
/* CornerBrackets — viewfinder marks (matches RunSweepDialog)                */
/* ========================================================================= */

function CornerBrackets() {
  const common =
    "absolute w-2 h-2 border-border-emphasis pointer-events-none";
  return (
    <>
      <span
        className={`${common} -top-px -left-px border-t border-l`}
        aria-hidden
      />
      <span
        className={`${common} -top-px -right-px border-t border-r`}
        aria-hidden
      />
      <span
        className={`${common} -bottom-px -left-px border-b border-l`}
        aria-hidden
      />
      <span
        className={`${common} -bottom-px -right-px border-b border-r`}
        aria-hidden
      />
    </>
  );
}
