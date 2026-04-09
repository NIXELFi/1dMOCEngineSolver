import { useMemo } from "react";
import LineChart from "./charts/LineChart";
import type { SimulationResultsData } from "./RpmDetail";

/* ========================================================================= */
/* Types                                                                     */
/* ========================================================================= */

interface PlenumPanelProps {
  results: SimulationResultsData;
}

/** A chart row for a single plenum trace: theta (deg), value. */
interface PlenumRow {
  theta: number;
  pressure?: number;   // bar
  temperature?: number; // K
  [extraKey: string]: number | boolean | undefined;
}

/* ========================================================================= */
/* Color assignments                                                          */
/*                                                                           */
/* Pulled from the SweepCurves palette:                                      */
/*   • Pressure → cool cyan (`#6BC5D8`) — matches the "fluid / flow"         */
/*     semantic used for intake pipes in PipeTraces.                         */
/*   • Temperature → warm amber (`#E8A34A`) — the only warm non-accent color */
/*     in the chart vocabulary, reserved for thermal quantities.             */
/* ========================================================================= */

const PRESSURE_COLOR = "#6BC5D8";
const TEMPERATURE_COLOR = "#E8A34A";

/* ========================================================================= */
/* PlenumPanel — the "Plenum" tab body inside RpmDetail                       */
/* ========================================================================= */

/**
 * PlenumPanel — two stacked line charts showing plenum pressure (bar)
 * and plenum temperature (K) vs crank angle for the last recorded cycle.
 *
 * Data layout:
 *   • `theta_history` is the shared x-axis (same one the orchestrator
 *     uses for cylinder and pipe probes) — we take the last 720° window
 *     so the chart never draws cycle-wrap lines.
 *   • `plenum_pressure` is converted Pa → bar (divide by 1e5).
 *   • `plenum_temperature` is K, no conversion.
 *
 * Reference line at 1.013 bar on the pressure chart gives the viewer an
 * immediate "above/below atmospheric" read — the most useful single
 * annotation on a plenum trace. The temperature chart has no reference
 * line; thermal quantities don't have a universal "zero".
 */
export default function PlenumPanel({ results }: PlenumPanelProps) {
  /* ---- Filter + shift the last 720° window ------------------------------ */
  const { pressureRows, temperatureRows, pMin, pMax } = useMemo(() => {
    const theta = results.theta_history;
    const pressure = results.plenum_pressure;
    const temperature = results.plenum_temperature;
    if (!theta || theta.length === 0) {
      return {
        pressureRows: [] as PlenumRow[],
        temperatureRows: [] as PlenumRow[],
        pMin: NaN,
        pMax: NaN,
      };
    }

    let maxTheta = -Infinity;
    for (const t of theta) {
      if (Number.isFinite(t) && t > maxTheta) maxTheta = t;
    }
    if (!Number.isFinite(maxTheta)) {
      return {
        pressureRows: [] as PlenumRow[],
        temperatureRows: [] as PlenumRow[],
        pMin: NaN,
        pMax: NaN,
      };
    }
    const cutoff = maxTheta - 720;

    const pressureRows: PlenumRow[] = [];
    const temperatureRows: PlenumRow[] = [];
    let pMin = Infinity;
    let pMax = -Infinity;
    const n = Math.min(theta.length, pressure.length, temperature.length);
    for (let k = 0; k < n; k++) {
      const t = theta[k];
      if (!Number.isFinite(t) || t < cutoff) continue;
      const p = pressure[k];
      const T = temperature[k];
      const shifted = t - cutoff;
      if (Number.isFinite(p)) {
        const pBar = p / 1e5;
        // Each row carries a constant `atm_ref` field so LineChart can draw
        // a second dashed series at the 1.013 bar atmospheric reference. This
        // is the cheapest way to get a horizontal reference line through the
        // existing LineChart wrapper without teaching it a new prop.
        pressureRows.push({ theta: shifted, pressure: pBar, atm_ref: 1.013 });
        if (pBar < pMin) pMin = pBar;
        if (pBar > pMax) pMax = pBar;
      }
      if (Number.isFinite(T)) {
        temperatureRows.push({ theta: shifted, temperature: T });
      }
    }
    return { pressureRows, temperatureRows, pMin, pMax };
  }, [results]);

  /* ---- Compute the simple scalar readouts for the header strips --------- */
  const pMean = useMemo(() => {
    if (pressureRows.length === 0) return NaN;
    let sum = 0;
    for (const r of pressureRows) sum += r.pressure ?? 0;
    return sum / pressureRows.length;
  }, [pressureRows]);

  const tMean = useMemo(() => {
    if (temperatureRows.length === 0) return NaN;
    let sum = 0;
    for (const r of temperatureRows) sum += r.temperature ?? 0;
    return sum / temperatureRows.length;
  }, [temperatureRows]);

  /* ---- Render ----------------------------------------------------------- */
  return (
    <div className="flex flex-col gap-2">
      {/* ===== Pressure ===================================================*/}
      <PlenumChartPanel
        ordinal="P1"
        title="Plenum Pressure"
        nPoints={pressureRows.length}
        accent={PRESSURE_COLOR}
        readout={
          Number.isFinite(pMean)
            ? [
                { label: "Mean", value: `${pMean.toFixed(3)} bar` },
                {
                  label: "Span",
                  value:
                    Number.isFinite(pMin) && Number.isFinite(pMax)
                      ? `${(pMax - pMin).toFixed(3)} bar`
                      : "—",
                },
              ]
            : []
        }
      >
        {pressureRows.length === 0 ? (
          <NoData height={250} />
        ) : (
          <LineChart
            data={pressureRows}
            xKey="theta"
            series={[
              { key: "pressure", label: "P", color: PRESSURE_COLOR },
              {
                key: "atm_ref",
                label: "Atm",
                color: "#565660",
                dashed: true,
              },
            ]}
            yLabel="P · BAR"
            height={250}
            showDots={false}
          />
        )}
      </PlenumChartPanel>

      {/* ===== Temperature =================================================*/}
      <PlenumChartPanel
        ordinal="P2"
        title="Plenum Temperature"
        nPoints={temperatureRows.length}
        accent={TEMPERATURE_COLOR}
        readout={
          Number.isFinite(tMean)
            ? [{ label: "Mean", value: `${tMean.toFixed(1)} K` }]
            : []
        }
      >
        {temperatureRows.length === 0 ? (
          <NoData height={250} />
        ) : (
          <LineChart
            data={temperatureRows}
            xKey="theta"
            series={[
              { key: "temperature", label: "T", color: TEMPERATURE_COLOR },
            ]}
            yLabel="T · K"
            height={250}
            showDots={false}
          />
        )}
      </PlenumChartPanel>
    </div>
  );
}

/* ========================================================================= */
/* PlenumChartPanel — bordered chrome for a single plenum chart              */
/*                                                                           */
/* Same grammar as CylinderPanel / PipePanel: swatch + bracketed ordinal +  */
/* uppercase title + a right-side readout cluster. Unlike the small pipe    */
/* panels, plenum charts also carry a scalar readout row (mean / span /    */
/* mean) so the viewer can skim the quantitative answer without reaching   */
/* for the tooltip.                                                         */
/* ========================================================================= */

function PlenumChartPanel({
  ordinal,
  title,
  nPoints,
  accent,
  readout,
  children,
}: {
  ordinal: string;
  title: string;
  nPoints: number;
  accent: string;
  readout: Array<{ label: string; value: string }>;
  children: React.ReactNode;
}) {
  return (
    <section
      className="flex flex-col bg-surface-raised border border-border-default rounded font-ui"
      aria-label={title}
    >
      {/* Header strip */}
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

        {/* Readout cluster — one or two compact key/value pairs */}
        {readout.map((r, i) => (
          <div
            key={i}
            className="flex items-center gap-1.5 px-3 border-l border-border-default"
          >
            <span className="text-[9px] font-mono uppercase tracking-[0.14em] text-text-muted leading-none">
              {r.label}
            </span>
            <span className="text-[10px] font-mono tabular-nums text-text-secondary leading-none">
              {r.value}
            </span>
          </div>
        ))}

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

      {/* Body */}
      <div className="p-3">{children}</div>
    </section>
  );
}

/* ========================================================================= */
/* NoData — in-panel empty state sized to the chart body                     */
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
