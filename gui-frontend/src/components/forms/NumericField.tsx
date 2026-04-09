import * as React from "react";

export interface NumericFieldProps {
  index: string;          // "01" — shown in the [NN] index mark
  label: string;
  unit: string;
  value: number;
  onChange: (next: number) => void;
  error?: string;
  inputRef?: React.Ref<HTMLInputElement>;
  step?: number;
  min?: number;
  /** Multiply the stored value by this when displaying; divide on input. */
  displayScale?: number;
}

/**
 * Numeric input matching the engine-sim instrument-chassis aesthetic.
 *
 * Shared by RunSweepDialog and the Config tab. Pattern: small [NN]
 * index mark on the left of the label row, label in muted small caps,
 * inline unit ornament on the right of the input, optional inline error
 * pinned to the right of the label row.
 */
export function NumericField({
  index,
  label,
  unit,
  value,
  onChange,
  error,
  inputRef,
  step,
  min,
  displayScale = 1,
}: NumericFieldProps) {
  const display = Number.isFinite(value) ? value * displayScale : NaN;

  const handle = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    if (raw === "") {
      onChange(NaN);
      return;
    }
    const parsed = Number(raw);
    onChange(parsed / displayScale);
  };

  return (
    <label className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-1.5">
          <span className="text-[9px] font-mono text-text-muted leading-none">
            [{index}]
          </span>
          <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-secondary leading-none">
            {label}
          </span>
        </div>
        {error && (
          <span className="text-[10px] font-mono text-status-error leading-none">
            {error}
          </span>
        )}
      </div>

      <div
        className={[
          "group flex items-stretch bg-surface border rounded",
          "transition-colors duration-150 ease-out",
          error
            ? "border-status-error/60 focus-within:border-status-error"
            : "border-border-default focus-within:border-border-emphasis",
        ].join(" ")}
      >
        <input
          ref={inputRef}
          type="number"
          value={Number.isNaN(display) ? "" : display}
          onChange={handle}
          step={step}
          min={min}
          inputMode="numeric"
          className={[
            "flex-1 min-w-0 bg-transparent outline-none",
            "px-3 py-2 text-sm font-mono tabular-nums text-text-primary",
            "placeholder:text-text-muted",
            "[appearance:textfield]",
            "[&::-webkit-outer-spin-button]:appearance-none [&::-webkit-outer-spin-button]:m-0",
            "[&::-webkit-inner-spin-button]:appearance-none [&::-webkit-inner-spin-button]:m-0",
          ].join(" ")}
        />
        <span className="flex items-center px-2 border-l border-border-default text-[9px] font-mono uppercase tracking-widest text-text-muted select-none">
          {unit}
        </span>
      </div>
    </label>
  );
}
