import { useMemo } from "react";
import LineChart, { type SeriesDef } from "./charts/LineChart";
import type { SimulationResultsData } from "./RpmDetail";

/* ========================================================================= */
/* Types                                                                     */
/* ========================================================================= */

interface CylinderTracesProps {
  results: SimulationResultsData;
}

/** A chart row for a single-cylinder trace: theta in deg, pressure in bar. */
interface CylRow {
  theta: number;
  pressure: number;
  [extraKey: string]: number | boolean | undefined;
}

/** A chart row for the overlay: theta in deg + one key per cylinder (bar). */
interface OverlayRow {
  theta: number;
  cyl_0?: number;
  cyl_1?: number;
  cyl_2?: number;
  cyl_3?: number;
  [extraKey: string]: number | boolean | undefined;
}

/** Per-cylinder derived display data. */
interface CylDerived {
  key: string;            // "0".."3"
  ordinal: string;        // "C1".."C4"
  label: string;          // "Cyl 1"
  title: string;          // "CYL 1"
  color: string;          // hex
  rows: CylRow[];         // filtered, shifted rows for the small chart
}

/* ========================================================================= */
/* Per-cylinder color assignments                                            */
/*                                                                           */
/* Pulled from tailwind.config.js `chart-*` tokens but inlined as raw hex    */
/* because LineChart takes literal strokes (Recharts can't resolve Tailwind  */
/* class names at runtime).                                                  */
/* ========================================================================= */

const CYL_COLORS = {
  "0": "#E5484D", // chart-power-ind — red
  "1": "#4493F8", // chart-power-brk — blue
  "2": "#3DD68C", // chart-ve — green
  "3": "#C586E8", // chart-restrictor — magenta
} as const;

/* ========================================================================= */
/* CylinderTraces — 4 thumbnail pressure traces + overlay                     */
/* ========================================================================= */

/**
 * CylinderTraces — the primary "Cylinders" tab body inside RpmDetail.
 *
 * Layout (per §4 of the design spec):
 *   • A 4-column grid of small per-cylinder pressure traces (150px tall).
 *   • Below, a larger overlay chart (250px tall) showing all 4 cylinders
 *     on the same axes for phase comparison.
 *
 * X-axis is crank angle, but the raw simulation `theta_history` values
 * run for the full simulated history (many cycles worth). To keep the
 * chart within a single 720° window without drawing connecting lines at
 * cycle wraps, we take only the LAST cycle of each cylinder's data
 * (points where theta >= maxTheta - 720) and shift the x-origin so the
 * window runs from 0 to 720. This is the "option (a)" approach and
 * sidesteps the NaN-insertion dance needed by option (b).
 *
 * Y-axis is pressure converted Pa → bar (divide by 1e5).
 */
export default function CylinderTraces({ results }: CylinderTracesProps) {
  /* ---- Per-cylinder derivation ------------------------------------------ */
  const cylinders = useMemo<CylDerived[]>(() => {
    const out: CylDerived[] = [];
    for (let i = 0; i < 4; i++) {
      const key = String(i);
      const cd = results.cylinder_data[key];
      const ordinal = `C${i + 1}`;
      const label = `Cyl ${i + 1}`;
      const title = `CYL ${i + 1}`;
      const color = CYL_COLORS[key as keyof typeof CYL_COLORS];

      if (!cd || !cd.theta || cd.theta.length === 0) {
        out.push({ key, ordinal, label, title, color, rows: [] });
        continue;
      }

      const { theta, pressure } = cd;
      // Find the max theta across the whole history.
      let maxTheta = -Infinity;
      for (const t of theta) {
        if (Number.isFinite(t) && t > maxTheta) maxTheta = t;
      }
      if (!Number.isFinite(maxTheta)) {
        out.push({ key, ordinal, label, title, color, rows: [] });
        continue;
      }
      const cutoff = maxTheta - 720;

      // Take points belonging to the last cycle, shifted to [0, 720].
      const rows: CylRow[] = [];
      const n = Math.min(theta.length, pressure.length);
      for (let k = 0; k < n; k++) {
        const t = theta[k];
        if (!Number.isFinite(t) || t < cutoff) continue;
        const p = pressure[k];
        if (!Number.isFinite(p)) continue;
        rows.push({
          theta: t - cutoff,
          pressure: p / 1e5,
        });
      }
      out.push({ key, ordinal, label, title, color, rows });
    }
    return out;
  }, [results]);

  /* ---- Overlay rows — join the 4 cylinders on the cyl-0 theta axis ------ */
  const overlayRows = useMemo<OverlayRow[]>(() => {
    // All cylinders share the same theta_history in the orchestrator, so
    // we can zip them index-for-index using cyl 0's filtered window as the
    // canonical sampling. But we still need to recompute the source index
    // mapping relative to the raw arrays because the small-chart rows are
    // already transformed. Re-running the filter here keeps the logic
    // explicit and avoids carrying hidden indices through the derived set.
    const cyl0 = results.cylinder_data["0"];
    if (!cyl0 || !cyl0.theta || cyl0.theta.length === 0) return [];

    let maxTheta = -Infinity;
    for (const t of cyl0.theta) {
      if (Number.isFinite(t) && t > maxTheta) maxTheta = t;
    }
    if (!Number.isFinite(maxTheta)) return [];
    const cutoff = maxTheta - 720;

    const cyl1 = results.cylinder_data["1"];
    const cyl2 = results.cylinder_data["2"];
    const cyl3 = results.cylinder_data["3"];

    const rows: OverlayRow[] = [];
    const n = cyl0.theta.length;
    for (let k = 0; k < n; k++) {
      const t = cyl0.theta[k];
      if (!Number.isFinite(t) || t < cutoff) continue;
      const row: OverlayRow = { theta: t - cutoff };
      const p0 = cyl0.pressure[k];
      if (Number.isFinite(p0)) row.cyl_0 = p0 / 1e5;
      if (cyl1) {
        const p = cyl1.pressure[k];
        if (Number.isFinite(p)) row.cyl_1 = p / 1e5;
      }
      if (cyl2) {
        const p = cyl2.pressure[k];
        if (Number.isFinite(p)) row.cyl_2 = p / 1e5;
      }
      if (cyl3) {
        const p = cyl3.pressure[k];
        if (Number.isFinite(p)) row.cyl_3 = p / 1e5;
      }
      rows.push(row);
    }
    return rows;
  }, [results]);

  /* ---- Overlay chart series definitions --------------------------------- */
  const overlaySeries: SeriesDef[] = [
    { key: "cyl_0", label: "Cyl 1", color: CYL_COLORS["0"] },
    { key: "cyl_1", label: "Cyl 2", color: CYL_COLORS["1"] },
    { key: "cyl_2", label: "Cyl 3", color: CYL_COLORS["2"] },
    { key: "cyl_3", label: "Cyl 4", color: CYL_COLORS["3"] },
  ];

  /* ---- Render ----------------------------------------------------------- */
  return (
    <div className="flex flex-col gap-2">
      {/* 4-up small traces */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-2">
        {cylinders.map((cyl) => (
          <CylinderPanel
            key={cyl.key}
            ordinal={cyl.ordinal}
            title={cyl.title}
            nPoints={cyl.rows.length}
            accent={cyl.color}
          >
            {cyl.rows.length === 0 ? (
              <NoData />
            ) : (
              <LineChart
                data={cyl.rows}
                xKey="theta"
                series={[{ key: "pressure", label: "P", color: cyl.color }]}
                yLabel="PRESSURE · BAR"
                height={150}
                showDots={false}
              />
            )}
          </CylinderPanel>
        ))}
      </div>

      {/* Overlay comparison chart */}
      <CylinderPanel
        ordinal="CX"
        title="All Cylinders"
        nPoints={overlayRows.length}
        accent="#8B8B95"
      >
        {overlayRows.length === 0 ? (
          <NoData />
        ) : (
          <LineChart
            data={overlayRows}
            xKey="theta"
            series={overlaySeries}
            yLabel="PRESSURE · BAR"
            height={250}
            showDots={false}
          />
        )}
      </CylinderPanel>
    </div>
  );
}

/* ========================================================================= */
/* CylinderPanel — the bordered chrome for each sub-chart                    */
/*                                                                           */
/* Mirrors the ChartPanel grammar from SweepCurves but tighter: a 2px        */
/* accent swatch in front of the bracketed ordinal gives each small trace   */
/* a memorable per-cylinder color without spamming the header.              */
/* ========================================================================= */

function CylinderPanel({
  ordinal,
  title,
  nPoints,
  accent,
  children,
}: {
  ordinal: string;
  title: string;
  nPoints: number;
  accent: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className="flex flex-col bg-surface-raised border border-border-default rounded font-ui"
      aria-label={title}
    >
      {/* Header strip */}
      <header className="flex items-stretch border-b border-border-default">
        <div className="flex-1 flex items-center gap-2 px-2.5 py-1.5 min-w-0">
          {/* Per-cylinder accent swatch */}
          <span
            className="inline-block w-[3px] h-3"
            style={{ backgroundColor: accent }}
            aria-hidden
          />
          <span className="text-[9px] font-mono text-text-muted leading-none tabular-nums">
            [{ordinal}]
          </span>
          <h4 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-text-primary leading-none truncate">
            {title}
          </h4>
        </div>

        <div className="flex items-center gap-1 px-2.5 border-l border-border-default">
          <span className="text-[9px] font-mono uppercase tracking-[0.14em] text-text-muted leading-none">
            n
          </span>
          <span className="text-[9px] font-mono text-text-muted leading-none">
            =
          </span>
          <span className="text-[9px] font-mono tabular-nums text-text-secondary leading-none">
            {formatCount(nPoints)}
          </span>
        </div>
      </header>

      {/* Body */}
      <div className="p-2.5">{children}</div>
    </section>
  );
}

/* ========================================================================= */
/* NoData — compact in-panel empty state                                     */
/* ========================================================================= */

function NoData() {
  return (
    <div className="h-[150px] flex flex-col items-center justify-center gap-2">
      <span
        className="inline-block w-1.5 h-1.5 rounded-full bg-text-muted"
        aria-hidden
      />
      <div className="w-10 h-px bg-border-default" aria-hidden />
      <span className="text-[9px] font-mono font-semibold uppercase tracking-[0.22em] text-text-muted leading-none">
        No Data
      </span>
    </div>
  );
}

/* ========================================================================= */
/* Helpers                                                                    */
/* ========================================================================= */

function formatCount(n: number): string {
  // Pad small counts for visual stability, let large counts breathe.
  if (n < 100) return String(n).padStart(2, "0");
  if (n < 10000) return String(n);
  // Switch to a compact form so the header strip stays predictable.
  return `${Math.round(n / 1000)}k`;
}
