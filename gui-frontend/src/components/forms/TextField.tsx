import * as React from "react";

export interface TextFieldProps {
  index: string;
  label: string;
  unit?: string;
  value: string;
  onChange: (next: string) => void;
  error?: string;
  placeholder?: string;
}

/**
 * String input matching NumericField's visual treatment. Used for `name`
 * and `firing_order` in the Config tab.
 */
export function TextField({
  index,
  label,
  unit,
  value,
  onChange,
  error,
  placeholder,
}: TextFieldProps) {
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
          "flex items-stretch bg-surface border rounded",
          "transition-colors duration-150 ease-out",
          error
            ? "border-status-error/60 focus-within:border-status-error"
            : "border-border-default focus-within:border-border-emphasis",
        ].join(" ")}
      >
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="flex-1 min-w-0 bg-transparent outline-none px-3 py-2 text-sm font-mono text-text-primary placeholder:text-text-muted"
        />
        {unit && (
          <span className="flex items-center px-2 border-l border-border-default text-[9px] font-mono uppercase tracking-widest text-text-muted select-none">
            {unit}
          </span>
        )}
      </div>
    </label>
  );
}
