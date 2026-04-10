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
