import { useMemo, type ReactElement } from "react";
import {
  LineChart as RechartsLineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ReferenceArea,
  ResponsiveContainer,
} from "recharts";

/* ========================================================================= */
/* Types                                                                     */
/* ========================================================================= */

export interface SeriesDef {
  /** Data key in the row objects (e.g. "indicated_power_hp"). */
  key: string;
  /** Legend label ("Indicated", "Brake", ...). */
  label: string;
  /** Raw hex color — Recharts needs a literal, not a tailwind token. */
  color: string;
  /** Dashed stroke variant. */
  dashed?: boolean;
}

/** One plottable row — a bag of numeric (and optionally extra) fields. */
export type ChartRow = Record<string, number | boolean | undefined>;

export interface LineChartProps {
  /** Rows of { rpm: 8000, indicated_power_hp: 89.9, ... }. */
  data: ChartRow[];
  /** The x-axis data key. Usually "rpm". */
  xKey: string;
  /** 1–3 series per chart. */
  series: SeriesDef[];
  /** Vertical left-edge label in uppercase mono. */
  yLabel: string;
  /** Chart body height in px. Defaults to 200. */
  height?: number;
  /** Currently selected RPM — draws an accent marker line + highlighted dot. */
  selectedRpm?: number | null;
  /** Fires when the user clicks a data point. Receives the x value (rpm). */
  onPointClick?: (rpm: number) => void;
  /** Ranges of x values to shade in the accent color (e.g. choked restrictor). */
  chokedRanges?: Array<[number, number]>;
  /**
   * Render a small filled dot at every data point. Default true — appropriate
   * for sparse charts like SweepCurves (10-30 points per chart) where the
   * dots help the eye locate individual measurements.
   *
   * Set to false for dense time-series charts (cylinder pressure traces,
   * pipe waves, plenum history) where data has thousands of points and
   * dots fuse into noise. The line stroke alone is more readable.
   */
  showDots?: boolean;
}

/* ========================================================================= */
/* Color tokens — duplicated here so the chart stays self-contained and       */
/* doesn't rely on resolving tailwind at runtime.                             */
/* ========================================================================= */

const COL = {
  border: "#25252B",
  borderEmph: "#3A3A42",
  // Brighter axis line tone — bright enough to be clearly visible against
  // the panel background but still recessed relative to the data strokes.
  axisLine: "#4A4A55",
  surfaceRaised: "#1A1A1F",
  textPrimary: "#F5F5F7",
  // Brighter axis label tone than text-secondary so the numeric tick
  // labels read cleanly against the dark panel background.
  axisLabel: "#B5B5C0",
  textSecondary: "#8B8B95",
  textMuted: "#565660",
  accent: "#FF4F1F",
} as const;

/* ========================================================================= */
/* LineChart — the wrapper                                                    */
/* ========================================================================= */

/**
 * Thin Recharts wrapper that enforces the SweepCurves chart conventions per
 * §5 of the design spec: hairline axes, no grid, single-stroke lines with
 * small filled dots, external legend, instrument-grade tooltip, vertical
 * y-axis label, and an optional accent-colored selection marker.
 *
 * This is deliberately *not* a general-purpose chart — it's tuned for the
 * 6-chart SweepCurves grid where every chart shares the same x-axis (RPM).
 */
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
}: LineChartProps) {
  const hasData = data.length > 0;

  /* -- Y-axis tick formatter. Picks precision based on value magnitude ---- */
  const formatYTick = useMemo(() => {
    // Compute rough span of all series values so we can choose precision.
    let max = -Infinity;
    let min = Infinity;
    for (const row of data) {
      for (const s of series) {
        const v = row[s.key];
        if (typeof v === "number" && Number.isFinite(v)) {
          if (v > max) max = v;
          if (v < min) min = v;
        }
      }
    }
    const span =
      Number.isFinite(max) && Number.isFinite(min) ? max - min : 0;
    const absMax = Math.max(Math.abs(max), Math.abs(min));

    return (value: number) => {
      if (!Number.isFinite(value)) return "";
      if (absMax >= 1000) return value.toFixed(0);
      if (span >= 10) return value.toFixed(0);
      if (span >= 1) return value.toFixed(1);
      return value.toFixed(2);
    };
  }, [data, series]);

  /* -- X-axis tick formatter — RPM values get no decimals, comma-free ----- */
  const formatXTick = (value: number) => {
    if (!Number.isFinite(value)) return "";
    return value.toFixed(0);
  };

  /* -- Click handler adapter for Recharts' Line.onClick ------------------- */
  const handleLineClick = (payload: unknown) => {
    if (!onPointClick) return;
    // Recharts passes the Line's datum state to Line.onClick; the `payload`
    // field holds the row object. We extract the xKey value from it.
    const obj = payload as { payload?: ChartRow } | undefined;
    const row = obj?.payload;
    const x = row?.[xKey];
    if (typeof x === "number") {
      onPointClick(x);
    }
  };

  return (
    <div className="relative font-ui">
      {/* ---- External legend (above the chart, never inside) ------------- */}
      <ChartLegend series={series} />

      {/* ---- Chart body with vertical y-label overlay -------------------- */}
      <div className="relative" style={{ height }}>
        {/* Vertical y-axis label — absolutely positioned on the left edge */}
        <div
          className="pointer-events-none absolute left-0 top-0 bottom-0 flex items-center justify-center"
          style={{ width: 14 }}
          aria-hidden
        >
          <span
            className="text-[9px] font-mono font-medium uppercase tracking-[0.18em] text-text-muted whitespace-nowrap leading-none"
            style={{
              transform: "rotate(-90deg)",
              transformOrigin: "center",
            }}
          >
            {yLabel}
          </span>
        </div>

        {/* Recharts container. Left margin accounts for the y-label gutter. */}
        <ResponsiveContainer width="100%" height="100%">
          <RechartsLineChart
            data={data}
            margin={{ top: 6, right: 10, bottom: 4, left: 14 }}
          >
            {/* ------ choked bands (restrictor chart) ------------------- */}
            {chokedRanges?.map(([x1, x2], i) => (
              <ReferenceArea
                key={`choked-${i}-${x1}-${x2}`}
                x1={x1}
                x2={x2}
                fill={COL.accent}
                fillOpacity={0.12}
                stroke="none"
                ifOverflow="extendDomain"
              />
            ))}

            {/* ------ selected rpm marker ------------------------------- */}
            {selectedRpm != null && hasData && (
              <ReferenceLine
                x={selectedRpm}
                stroke={COL.accent}
                strokeWidth={1}
                ifOverflow="extendDomain"
              />
            )}

            {/* ------ x-axis: hairline, mono, minimal ticks ------------ */}
            <XAxis
              dataKey={xKey}
              type="number"
              domain={["dataMin", "dataMax"]}
              stroke={COL.axisLine}
              strokeWidth={1}
              tick={{
                fill: COL.axisLabel,
                fontSize: 11,
                fontFamily:
                  "'JetBrains Mono', ui-monospace, monospace",
              }}
              tickLine={{ stroke: COL.axisLine, strokeWidth: 1 }}
              axisLine={{ stroke: COL.axisLine, strokeWidth: 1 }}
              tickMargin={6}
              tickCount={6}
              tickFormatter={formatXTick}
              allowDecimals={false}
              minTickGap={12}
            />

            {/* ------ y-axis: hairline, mono, minimal ticks ------------ */}
            <YAxis
              stroke={COL.axisLine}
              strokeWidth={1}
              tick={{
                fill: COL.axisLabel,
                fontSize: 11,
                fontFamily:
                  "'JetBrains Mono', ui-monospace, monospace",
              }}
              tickLine={{ stroke: COL.axisLine, strokeWidth: 1 }}
              axisLine={{ stroke: COL.axisLine, strokeWidth: 1 }}
              tickMargin={4}
              tickCount={5}
              tickFormatter={formatYTick}
              width={44}
              domain={["auto", "auto"]}
            />

            {/* ------ custom tooltip ----------------------------------- */}
            <Tooltip
              cursor={{
                stroke: COL.borderEmph,
                strokeWidth: 1,
                strokeDasharray: "2 3",
              }}
              isAnimationActive={false}
              content={
                <InstrumentTooltip
                  series={series}
                  xKey={xKey}
                  formatYTick={formatYTick}
                />
              }
            />

            {/* ------ one <Line> per series ---------------------------- */}
            {series.map((s) => {
              // When showDots is true, render the regular series dots and
              // the accent-colored selection halo. When false (dense
              // time-series), we still want the selected-point halo IF a
              // selection is active, but no per-point dots.
              const renderDot = (dotProps: any) => {
                if (!showDots) {
                  // Only render the selection halo, not the regular dot
                  return renderSelectionHaloOnly(
                    dotProps as DotRenderProps,
                    xKey,
                    selectedRpm,
                  );
                }
                return renderSelectionDot(
                  dotProps as DotRenderProps,
                  s.color,
                  xKey,
                  selectedRpm,
                );
              };

              return (
                <Line
                  key={s.key}
                  type="linear"
                  dataKey={s.key}
                  stroke={s.color}
                  strokeWidth={1.75}
                  strokeDasharray={s.dashed ? "4 3" : undefined}
                  dot={renderDot}
                  activeDot={{
                    r: 5,
                    fill: s.color,
                    stroke: COL.surfaceRaised,
                    strokeWidth: 1.5,
                  }}
                  isAnimationActive={false}
                  connectNulls
                  onClick={handleLineClick}
                />
              );
            })}
          </RechartsLineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ========================================================================= */
/* ChartLegend — a small row of color squares + uppercase labels            */
/* ========================================================================= */

function ChartLegend({ series }: { series: SeriesDef[] }) {
  return (
    <div
      className="flex items-center gap-3 pb-2 mb-1 border-b border-border-default/60"
      aria-hidden
    >
      {series.map((s) => (
        <div
          key={s.key}
          className="flex items-center gap-1.5 leading-none"
        >
          {/* color swatch — solid for continuous, two dashes for dashed */}
          {s.dashed ? (
            <span className="flex items-center gap-[2px]" aria-hidden>
              <span
                className="block w-[5px] h-[2px]"
                style={{ backgroundColor: s.color }}
              />
              <span
                className="block w-[5px] h-[2px]"
                style={{ backgroundColor: s.color }}
              />
            </span>
          ) : (
            <span
              className="block w-3 h-[2px]"
              style={{ backgroundColor: s.color }}
              aria-hidden
            />
          )}
          <span className="text-[9px] font-medium uppercase tracking-[0.14em] text-text-secondary">
            {s.label}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ========================================================================= */
/* renderSelectionDot — custom dot renderer                                  */
/*                                                                           */
/* Recharts invokes this for every plotted data point. When the point's x   */
/* value matches selectedRpm, we render a filled accent circle with an     */
/* outer "breath ring"; otherwise a normal 3px series-colored circle.       */
/* ========================================================================= */

interface DotRenderProps {
  cx?: number;
  cy?: number;
  payload?: ChartRow;
  index?: number;
  key?: string;
}

function renderSelectionDot(
  props: DotRenderProps,
  color: string,
  xKey: string,
  selectedRpm: number | null,
): ReactElement<SVGElement> {
  const { cx, cy, payload, index } = props;

  // Recharts occasionally calls dot renderers with missing coordinates
  // (e.g. during legend re-renders). Returning an empty <g> satisfies the
  // ReactElement<SVGElement> contract in all cases.
  if (typeof cx !== "number" || typeof cy !== "number" || !payload) {
    return <g key={`empty-dot-${index ?? 0}`} />;
  }

  const xVal = payload[xKey];
  const isSelected =
    selectedRpm != null && typeof xVal === "number" && xVal === selectedRpm;

  if (isSelected) {
    return (
      <g key={`sel-dot-${index ?? cx}`}>
        {/* Outer breath ring */}
        <circle cx={cx} cy={cy} r={7} fill={COL.accent} fillOpacity={0.18} />
        {/* Core */}
        <circle
          cx={cx}
          cy={cy}
          r={4}
          fill={COL.accent}
          stroke={COL.surfaceRaised}
          strokeWidth={1.5}
        />
      </g>
    );
  }

  return (
    <g key={`dot-${index ?? cx}`}>
      <circle
        cx={cx}
        cy={cy}
        r={3}
        fill={color}
        stroke={COL.surfaceRaised}
        strokeWidth={1}
      />
    </g>
  );
}

/**
 * Variant for dense time-series charts: only renders the accent selection
 * halo at the selected x value (if any). Returns an empty <g> for every
 * other data point so the chart shows just the line stroke without dot
 * noise on top.
 */
function renderSelectionHaloOnly(
  props: DotRenderProps,
  xKey: string,
  selectedRpm: number | null,
): ReactElement<SVGElement> {
  const { cx, cy, payload, index } = props;

  if (typeof cx !== "number" || typeof cy !== "number" || !payload) {
    return <g key={`empty-dot-${index ?? 0}`} />;
  }

  const xVal = payload[xKey];
  const isSelected =
    selectedRpm != null && typeof xVal === "number" && xVal === selectedRpm;

  if (isSelected) {
    return (
      <g key={`sel-dot-${index ?? cx}`}>
        <circle cx={cx} cy={cy} r={7} fill={COL.accent} fillOpacity={0.18} />
        <circle
          cx={cx}
          cy={cy}
          r={4}
          fill={COL.accent}
          stroke={COL.surfaceRaised}
          strokeWidth={1.5}
        />
      </g>
    );
  }

  // No dot — caller wanted line stroke only
  return <g key={`empty-dot-${index ?? cx}`} />;
}

/* ========================================================================= */
/* InstrumentTooltip — custom Recharts tooltip                               */
/*                                                                           */
/* Dark surface, 1px hairline border, mono tabular-nums, table-style rows    */
/* with series color dot + right-aligned numeric values. Top row shows the   */
/* x value (RPM 8000).                                                       */
/* ========================================================================= */

interface TooltipPayloadEntry {
  value?: number;
  dataKey?: string;
  payload?: ChartRow;
}

interface TooltipContentProps {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
  label?: number;
}

function InstrumentTooltip({
  active,
  payload,
  label,
  series,
  xKey,
  formatYTick,
}: TooltipContentProps & {
  series: SeriesDef[];
  xKey: string;
  formatYTick: (value: number) => string;
}) {
  if (!active || !payload || payload.length === 0) return null;

  const row = payload[0]?.payload;
  const xVal = typeof label === "number" ? label : row ? row[xKey] : undefined;

  return (
    <div
      className="bg-surface-raised border border-border-default rounded font-ui"
      style={{
        padding: "6px 8px",
        minWidth: 140,
        boxShadow: "0 1px 0 rgba(0, 0, 0, 0.4)",
      }}
    >
      {/* Header: xKey value in uppercase with small hairline below */}
      <div className="flex items-baseline justify-between gap-3 pb-1 mb-1 border-b border-border-default">
        <span className="text-[8px] font-semibold uppercase tracking-[0.2em] text-text-muted leading-none">
          {xKey}
        </span>
        <span className="text-[11px] font-mono tabular-nums font-medium text-text-primary leading-none">
          {typeof xVal === "number" ? xVal.toFixed(0) : "—"}
        </span>
      </div>

      {/* Per-series rows */}
      <table className="w-full border-collapse">
        <tbody>
          {series.map((s) => {
            const entry = payload.find((p) => p.dataKey === s.key);
            const v = entry?.value;
            return (
              <tr key={s.key} className="align-baseline">
                <td className="pr-1.5 py-[1px]">
                  <span
                    className="inline-block w-[6px] h-[6px]"
                    style={{
                      backgroundColor: s.color,
                      borderRadius: 1,
                    }}
                    aria-hidden
                  />
                </td>
                <td className="py-[1px]">
                  <span className="text-[9px] uppercase tracking-[0.12em] text-text-secondary leading-none">
                    {s.label}
                  </span>
                </td>
                <td className="pl-3 py-[1px] text-right">
                  <span className="text-[10px] font-mono tabular-nums text-text-primary leading-none">
                    {typeof v === "number" && Number.isFinite(v)
                      ? formatYTick(v)
                      : "—"}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
