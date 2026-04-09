import { useMemo } from "react";
import LineChart from "./charts/LineChart";
import type { SimulationResultsData } from "./RpmDetail";

/* ========================================================================= */
/* Types                                                                     */
/* ========================================================================= */

interface RestrictorPanelProps {
  results: SimulationResultsData;
}

/** A chart row: theta (deg), mdot (g/s). */
interface RestrictorRow {
  theta: number;
  mdot: number;
  [extraKey: string]: number | boolean | undefined;
}

/* ========================================================================= */
/* Accent                                                                     */
/*                                                                           */
/* The restrictor gets `chart-restrictor` magenta per the SweepCurves        */
/* palette (matches the "Restrictor · g/s" panel in the top region so the   */
/* viewer can visually link a detail trace to its curve).                    */
/* ========================================================================= */

const RESTRICTOR_COLOR = "#C586E8";

/* ========================================================================= */
/* RestrictorPanel — the "Restrictor" tab body inside RpmDetail               */
/* ========================================================================= */

/**
 * RestrictorPanel — a single large mdot-vs-theta chart with a red shaded
 * band wherever `restrictor_choked === true`, plus a 2x2 scalar readout
 * grid below the chart.
 *
 * Unit conversion: backend emits kg/s, we display g/s (multiply by 1000)
 * because the SweepCurves "Restrictor · g/s" panel uses the same unit.
 *
 * The shaded-choked-band is constructed by scanning `restrictor_choked`
 * and emitting contiguous [theta_start, theta_end] pairs, which is what
 * the LineChart's `chokedRanges` prop expects. Same algorithm that
 * SweepCurves uses for its rpm-axis choking band, just adapted to a
 * crank-angle x-axis.
 *
 * Below the chart: a 2x2 grid of scalar readouts — peak mdot, mean mdot,
 * choked time fraction, and peak choked span. Per-cycle intake mass is
 * NOT surfaced here because the backend per-RPM results payload doesn't
 * include the perf dict (that lives one level up on the sweep snapshot).
 * The agent brief calls this out explicitly.
 */
export default function RestrictorPanel({ results }: RestrictorPanelProps) {
  /* ---- Filter/shift the last 720° window -------------------------------- */
  const { rows, chokedRanges, peakMdot, meanMdot, chokedFrac, peakChokedSpan } =
    useMemo(() => {
      const theta = results.theta_history;
      const mdot = results.restrictor_mdot;
      const choked = results.restrictor_choked;

      if (!theta || theta.length === 0) {
        return {
          rows: [] as RestrictorRow[],
          chokedRanges: [] as Array<[number, number]>,
          peakMdot: NaN,
          meanMdot: NaN,
          chokedFrac: NaN,
          peakChokedSpan: NaN,
        };
      }

      let maxTheta = -Infinity;
      for (const t of theta) {
        if (Number.isFinite(t) && t > maxTheta) maxTheta = t;
      }
      if (!Number.isFinite(maxTheta)) {
        return {
          rows: [] as RestrictorRow[],
          chokedRanges: [] as Array<[number, number]>,
          peakMdot: NaN,
          meanMdot: NaN,
          chokedFrac: NaN,
          peakChokedSpan: NaN,
        };
      }
      const cutoff = maxTheta - 720;

      const rows: RestrictorRow[] = [];
      const chokedFlags: boolean[] = [];
      let peakMdot = -Infinity;
      let sumMdot = 0;
      let count = 0;
      let chokedCount = 0;

      const n = Math.min(theta.length, mdot.length, choked.length);
      for (let k = 0; k < n; k++) {
        const t = theta[k];
        if (!Number.isFinite(t) || t < cutoff) continue;
        const m = mdot[k];
        if (!Number.isFinite(m)) continue;
        const mgs = m * 1000;
        const shifted = t - cutoff;
        rows.push({ theta: shifted, mdot: mgs });
        chokedFlags.push(!!choked[k]);
        if (mgs > peakMdot) peakMdot = mgs;
        sumMdot += mgs;
        count += 1;
        if (choked[k]) chokedCount += 1;
      }

      // Build contiguous choked [start, end] theta ranges.
      const chokedRanges: Array<[number, number]> = [];
      let rangeStart: number | null = null;
      let rangeLast: number | null = null;
      for (let k = 0; k < rows.length; k++) {
        if (chokedFlags[k]) {
          if (rangeStart == null) rangeStart = rows[k].theta;
          rangeLast = rows[k].theta;
        } else if (rangeStart != null && rangeLast != null) {
          chokedRanges.push([rangeStart, rangeLast]);
          rangeStart = null;
          rangeLast = null;
        }
      }
      if (rangeStart != null && rangeLast != null) {
        chokedRanges.push([rangeStart, rangeLast]);
      }

      // Peak contiguous span (deg) — useful sanity read for tuners.
      let peakChokedSpan = 0;
      for (const [a, b] of chokedRanges) {
        const w = b - a;
        if (w > peakChokedSpan) peakChokedSpan = w;
      }

      return {
        rows,
        chokedRanges,
        peakMdot: count > 0 ? peakMdot : NaN,
        meanMdot: count > 0 ? sumMdot / count : NaN,
        chokedFrac: count > 0 ? (chokedCount / count) * 100 : NaN,
        peakChokedSpan: chokedRanges.length > 0 ? peakChokedSpan : NaN,
      };
    }, [results]);

  /* ---- Render ----------------------------------------------------------- */
  return (
    <div className="flex flex-col gap-2">
      <RestrictorChartPanel
        ordinal="R1"
        title="Restrictor Mass Flow"
        nPoints={rows.length}
        accent={RESTRICTOR_COLOR}
        chokedActive={chokedRanges.length > 0}
      >
        {rows.length === 0 ? (
          <NoData height={260} />
        ) : (
          <LineChart
            data={rows}
            xKey="theta"
            series={[
              { key: "mdot", label: "ṁ", color: RESTRICTOR_COLOR },
            ]}
            yLabel="ṁ · g/s"
            height={260}
            chokedRanges={chokedRanges}
            showDots={false}
          />
        )}
      </RestrictorChartPanel>

      {/* ================================================================= */}
      {/* Scalar readout grid — a 2x2 Bloomberg-esque instrument panel      */}
      {/* ================================================================= */}
      <ReadoutGrid
        items={[
          {
            label: "Peak ṁ",
            value: formatValue(peakMdot, 2, "g/s"),
          },
          {
            label: "Mean ṁ",
            value: formatValue(meanMdot, 2, "g/s"),
          },
          {
            label: "Choked Time",
            value: formatValue(chokedFrac, 1, "%"),
            warn: Number.isFinite(chokedFrac) && chokedFrac > 0,
          },
          {
            label: "Peak Choke Span",
            value: formatValue(peakChokedSpan, 1, "°"),
            warn: Number.isFinite(peakChokedSpan) && peakChokedSpan > 0,
          },
        ]}
      />
    </div>
  );
}

/* ========================================================================= */
/* RestrictorChartPanel — the bordered chrome for the single big chart       */
/*                                                                           */
/* Adds a "CHOKED" badge in the right cluster when any point in the window  */
/* is choked — mirrors the SweepCurves restrictor panel's badge.             */
/* ========================================================================= */

function RestrictorChartPanel({
  ordinal,
  title,
  nPoints,
  accent,
  chokedActive,
  children,
}: {
  ordinal: string;
  title: string;
  nPoints: number;
  accent: string;
  chokedActive: boolean;
  children: React.ReactNode;
}) {
  return (
    <section
      className="flex flex-col bg-surface-raised border border-border-default rounded font-ui"
      aria-label={title}
    >
      <header className="flex items-stretch border-b border-border-default">
        <div className="flex-1 flex items-center gap-2 px-3 py-1.5 min-w-0">
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

        {chokedActive && (
          <div className="flex items-center gap-1.5 px-3 border-l border-border-default">
            <span
              className="inline-block w-1.5 h-1.5 rounded-full bg-accent"
              aria-hidden
            />
            <span className="text-[9px] font-mono font-semibold uppercase tracking-[0.18em] text-accent leading-none">
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
            {formatCount(nPoints)}
          </span>
        </div>
      </header>

      <div className="p-3">{children}</div>
    </section>
  );
}

/* ========================================================================= */
/* ReadoutGrid — 2x2 scalar readout panel                                    */
/*                                                                           */
/* Each cell is a label/value pair in the instrument-panel grammar: tiny    */
/* uppercase label on top, mono tabular-nums value below. Cells are split  */
/* by 1px hairlines (not borders on each cell — that would look like       */
/* buttons). Warn cells dim to the accent color as a soft alert without    */
/* reaching for the red `status-error` shade.                               */
/* ========================================================================= */

function ReadoutGrid({
  items,
}: {
  items: Array<{ label: string; value: string; warn?: boolean }>;
}) {
  return (
    <section
      className="bg-surface-raised border border-border-default rounded font-ui"
      aria-label="Restrictor scalar readouts"
    >
      <div className="grid grid-cols-2 divide-x divide-border-default">
        {items.map((item, i) => (
          <div
            key={item.label}
            className={[
              "flex flex-col gap-1 px-4 py-3",
              // Top row vs bottom row hairline
              i < 2 ? "border-b border-border-default" : "",
            ].join(" ")}
          >
            <span className="text-[9px] font-mono font-semibold uppercase tracking-[0.2em] text-text-muted leading-none">
              {item.label}
            </span>
            <span
              className={[
                "text-xl font-mono font-medium tabular-nums leading-none",
                item.warn ? "text-accent" : "text-text-primary",
              ].join(" ")}
            >
              {item.value}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ========================================================================= */
/* NoData — in-panel empty state                                             */
/* ========================================================================= */

function NoData({ height }: { height: number }) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-2"
      style={{ height }}
    >
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
  if (n < 100) return String(n).padStart(2, "0");
  if (n < 10000) return String(n);
  return `${Math.round(n / 1000)}k`;
}

function formatValue(v: number, decimals: number, unit: string): string {
  if (!Number.isFinite(v)) return "—";
  return `${v.toFixed(decimals)} ${unit}`;
}
