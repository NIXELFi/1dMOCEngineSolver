import { useEffect, useMemo, useRef, useState } from "react";
import { X } from "lucide-react";
import { api, type ConfigSummary, type StartSweepParams } from "../api/client";
import { NumericField } from "./forms/NumericField";
import { CornerBrackets } from "./forms/CornerBrackets";
import {
  useConfigStore,
  selectIsDirty,
} from "../state/configStore";

interface RunSweepDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

interface FormState {
  rpm_start: number;
  rpm_end: number;
  rpm_step: number;
  n_cycles: number;
  n_workers: number;
  config_name: string;
}

const DEFAULTS: FormState = {
  rpm_start: 6000,
  rpm_end: 13000,
  rpm_step: 1000,
  n_cycles: 12,
  n_workers: 8,
  config_name: "",
};

/**
 * RunSweepDialog — modal form for dispatching a new parallel RPM sweep.
 *
 * Design direction (per 2026-04-08-engine-sim-gui-v1-design.md §5): this is
 * a dispatch console, not a contact form. Bracketed corner marks on the
 * chassis, numbered field rows like an ordnance checklist, a live-computed
 * "RPM POINTS" readout in the header, a 16-notch discrete worker slider,
 * JetBrains Mono tabular-nums on every numeric. Sharp 1px hairlines, 4px
 * inputs, 6px modal, fade-in only. Accent color appears exactly once — on
 * the START SWEEP button.
 */
export default function RunSweepDialog({ isOpen, onClose }: RunSweepDialogProps) {
  const [form, setForm] = useState<FormState>(DEFAULTS);
  const [configs, setConfigs] = useState<ConfigSummary[]>([]);
  const [configsLoading, setConfigsLoading] = useState(false);
  const [configsError, setConfigsError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeName = useConfigStore((s) => s.activeName);
  const isDirty = useConfigStore(selectIsDirty);

  const firstFieldRef = useRef<HTMLInputElement | null>(null);

  /* ---------------------------------------------------------------------- */
  /* Config list — fetched on mount, default selected                       */
  /* ---------------------------------------------------------------------- */

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setConfigsLoading(true);
    setConfigsError(null);
    api
      .listConfigs()
      .then((list) => {
        if (cancelled) return;
        setConfigs(list);
        setForm((prev) => {
          if (prev.config_name && list.some((c) => c.name === prev.config_name)) {
            return prev;
          }
          const fromStore =
            activeName && list.some((c) => c.name === activeName) ? activeName : null;
          const fallback = list.find((c) => c.name === "cbr600rr.json") ?? list[0];
          const next = fromStore ? { name: fromStore } : fallback;
          return next ? { ...prev, config_name: next.name } : prev;
        });
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setConfigsError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setConfigsLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // activeName is read inside the effect but we intentionally don't re-fetch
    // configs when it changes — the user may have picked a different option
    // from the dropdown, and the store value is only consulted on open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  /* ---------------------------------------------------------------------- */
  /* Reset transient state + autofocus when opened                          */
  /* ---------------------------------------------------------------------- */

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    setSubmitting(false);
    // autofocus first field next frame so the dialog has mounted
    const id = window.setTimeout(() => {
      firstFieldRef.current?.focus();
      firstFieldRef.current?.select();
    }, 0);
    return () => window.clearTimeout(id);
  }, [isOpen]);

  /* ---------------------------------------------------------------------- */
  /* Escape key closes                                                      */
  /* ---------------------------------------------------------------------- */

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  /* ---------------------------------------------------------------------- */
  /* Validation                                                             */
  /* ---------------------------------------------------------------------- */

  const fieldErrors = useMemo(() => {
    const errs: Partial<Record<keyof FormState, string>> = {};
    if (!Number.isFinite(form.rpm_start) || form.rpm_start < 0) {
      errs.rpm_start = "must be >= 0";
    }
    if (!Number.isFinite(form.rpm_end) || form.rpm_end <= form.rpm_start) {
      errs.rpm_end = "must exceed RPM start";
    }
    if (!Number.isFinite(form.rpm_step) || form.rpm_step <= 0) {
      errs.rpm_step = "must be > 0";
    }
    if (!Number.isInteger(form.n_cycles) || form.n_cycles < 1) {
      errs.n_cycles = "must be >= 1";
    }
    if (
      !Number.isInteger(form.n_workers) ||
      form.n_workers < 1 ||
      form.n_workers > 16
    ) {
      errs.n_workers = "1 – 16";
    }
    if (!form.config_name.trim()) {
      errs.config_name = "select a config";
    }
    return errs;
  }, [form]);

  const isValid = Object.keys(fieldErrors).length === 0;

  /* ---------------------------------------------------------------------- */
  /* Computed readouts                                                      */
  /* ---------------------------------------------------------------------- */

  const rpmPointCount = useMemo(() => {
    if (fieldErrors.rpm_start || fieldErrors.rpm_end || fieldErrors.rpm_step) {
      return null;
    }
    const span = form.rpm_end - form.rpm_start;
    return Math.floor(span / form.rpm_step) + 1;
  }, [form.rpm_start, form.rpm_end, form.rpm_step, fieldErrors]);

  /* ---------------------------------------------------------------------- */
  /* Handlers                                                               */
  /* ---------------------------------------------------------------------- */

  const setField = (key: keyof FormState) => (next: number) => {
    setForm((prev) => ({ ...prev, [key]: next }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const params: StartSweepParams = {
        rpm_start: form.rpm_start,
        rpm_end: form.rpm_end,
        rpm_step: form.rpm_step,
        n_cycles: form.n_cycles,
        n_workers: form.n_workers,
        config_name: form.config_name,
      };
      await api.startSweep(params);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  /* ---------------------------------------------------------------------- */
  /* Render                                                                 */
  /* ---------------------------------------------------------------------- */

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="run-sweep-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center px-4 animate-[rsd-fade_200ms_ease-out]"
    >
      {/* Local keyframes — scoped to this component, fade-in only (opacity). */}
      <style>{`@keyframes rsd-fade { from { opacity: 0 } to { opacity: 1 } }`}</style>

      {/* Backdrop ---------------------------------------------------------- */}
      <button
        type="button"
        aria-label="Close dialog"
        onClick={onClose}
        className="absolute inset-0 bg-bg/70 backdrop-blur-sm cursor-default"
      />

      {/* Panel wrapper (corner brackets live here) ------------------------- */}
      <div className="relative w-full max-w-md">
        <CornerBrackets />

        <div className="relative bg-surface-raised border border-border-default rounded-md font-ui">
          {/* Header ---------------------------------------------------------- */}
          <header className="flex items-stretch border-b border-border-default">
            <div className="flex-1 flex items-center gap-3 px-4 py-3">
              <span
                className="inline-block w-1.5 h-1.5 rounded-full bg-accent"
                aria-hidden
              />
              <h2
                id="run-sweep-dialog-title"
                className="text-[12px] font-semibold uppercase tracking-[0.2em] text-text-primary leading-none"
              >
                Run Sweep
              </h2>
              <span className="text-[9px] font-mono uppercase tracking-[0.18em] text-text-muted leading-none border border-border-default px-1 py-[1px]">
                Dispatch
              </span>
            </div>

            {/* Live RPM points readout */}
            <div className="flex flex-col justify-center gap-0.5 px-4 border-l border-border-default min-w-[96px]">
              <span className="text-[9px] font-medium uppercase tracking-[0.18em] text-text-muted leading-none">
                RPM Points
              </span>
              <span className="text-[13px] font-mono font-medium tabular-nums leading-none">
                {rpmPointCount !== null ? (
                  <span className="text-text-primary">
                    {String(rpmPointCount).padStart(2, "0")}
                  </span>
                ) : (
                  <span className="text-text-muted">—</span>
                )}
              </span>
            </div>

            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="flex items-center justify-center w-11 border-l border-border-default text-text-muted hover:text-text-primary hover:bg-surface transition-colors duration-150 ease-out"
            >
              <X className="w-4 h-4" strokeWidth={1.8} />
            </button>
          </header>

          {/* Form ------------------------------------------------------------ */}
          <form onSubmit={handleSubmit} noValidate>
            <div className="px-4 py-4 flex flex-col gap-3">
              {/* Row: RPM Start / RPM End --------------------------------- */}
              <div className="grid grid-cols-2 gap-3">
                <NumericField
                  index="01"
                  label="RPM Start"
                  unit="rpm"
                  value={form.rpm_start}
                  onChange={setField("rpm_start")}
                  error={fieldErrors.rpm_start}
                  inputRef={firstFieldRef}
                  step={100}
                  min={0}
                />
                <NumericField
                  index="02"
                  label="RPM End"
                  unit="rpm"
                  value={form.rpm_end}
                  onChange={setField("rpm_end")}
                  error={fieldErrors.rpm_end}
                  step={100}
                  min={0}
                />
              </div>

              {/* Row: RPM Step / Cycles ----------------------------------- */}
              <div className="grid grid-cols-2 gap-3">
                <NumericField
                  index="03"
                  label="RPM Step"
                  unit="rpm"
                  value={form.rpm_step}
                  onChange={setField("rpm_step")}
                  error={fieldErrors.rpm_step}
                  step={50}
                  min={1}
                />
                <NumericField
                  index="04"
                  label="Cycles"
                  unit="n"
                  value={form.n_cycles}
                  onChange={setField("n_cycles")}
                  error={fieldErrors.n_cycles}
                  step={1}
                  min={1}
                />
              </div>

              {/* Row: Workers (number + discrete tick slider) ------------- */}
              <WorkersField
                value={form.n_workers}
                onChange={(n) => setForm((p) => ({ ...p, n_workers: n }))}
                error={fieldErrors.n_workers}
              />

              {/* Row: Config dropdown ------------------------------------- */}
              <ConfigField
                value={form.config_name}
                onChange={(name) =>
                  setForm((prev) => ({ ...prev, config_name: name }))
                }
                configs={configs}
                loading={configsLoading}
                loadError={configsError}
                error={fieldErrors.config_name}
              />

              {/* Dirty-state warning strip -------------------------------- */}
              {isDirty && form.config_name === activeName && (
                <div className="border border-accent/40 bg-accent/[0.06] px-3 py-2">
                  <div className="flex items-start gap-2">
                    <span
                      className="mt-[5px] inline-block w-1.5 h-1.5 rounded-full bg-accent flex-shrink-0"
                      aria-hidden
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-[9px] font-semibold uppercase tracking-[0.2em] text-accent leading-none mb-1">
                        Unsaved Changes
                      </div>
                      <div className="text-xs text-text-primary font-mono break-words leading-snug">
                        Active config has unsaved edits — sweep will use the saved version on disk.
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Error strip ------------------------------------------------ */}
            {error && (
              <div className="mx-4 mb-3 border border-status-error/40 bg-status-error/[0.06] px-3 py-2">
                <div className="flex items-start gap-2">
                  <span
                    className="mt-[5px] inline-block w-1.5 h-1.5 rounded-full bg-status-error flex-shrink-0"
                    aria-hidden
                  />
                  <div className="flex-1 min-w-0">
                    <div className="text-[9px] font-semibold uppercase tracking-[0.2em] text-status-error leading-none mb-1">
                      Dispatch Failed
                    </div>
                    <div className="text-xs text-text-primary font-mono break-words leading-snug">
                      {error}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Footer ----------------------------------------------------- */}
            <footer className="flex items-stretch border-t border-border-default">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 h-11 border-r border-border-default text-[11px] font-medium uppercase tracking-[0.18em] text-text-secondary hover:bg-surface hover:text-text-primary transition-colors duration-150 ease-out"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!isValid || submitting}
                className={[
                  "flex-[2] h-11 inline-flex items-center justify-center gap-2",
                  "text-[11px] font-semibold uppercase tracking-[0.2em] leading-none",
                  "transition-colors duration-150 ease-out",
                  !isValid || submitting
                    ? "bg-accent/20 text-accent/50 cursor-not-allowed"
                    : "bg-accent text-bg hover:bg-[#FF6A3D] active:bg-accent-dim",
                ].join(" ")}
              >
                {submitting ? (
                  <>
                    <Spinner />
                    <span>Dispatching…</span>
                  </>
                ) : (
                  <>
                    <span
                      className="inline-block w-1.5 h-1.5 rounded-full bg-current"
                      aria-hidden
                    />
                    <span>Start Sweep</span>
                  </>
                )}
              </button>
            </footer>
          </form>
        </div>
      </div>
    </div>
  );
}

/* ========================================================================= */
/* WorkersField — numeric input + discrete 16-notch slider                   */
/* ========================================================================= */

function WorkersField({
  value,
  onChange,
  error,
}: {
  value: number;
  onChange: (n: number) => void;
  error?: string;
}) {
  const safe = Number.isFinite(value) ? value : 0;
  const clamped = Math.max(1, Math.min(16, Math.round(safe)));
  const fillPct = ((clamped - 1) / 15) * 100;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-1.5">
          <span className="text-[9px] font-mono text-text-muted leading-none">
            [05]
          </span>
          <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-secondary leading-none">
            Workers
          </span>
        </div>
        {error ? (
          <span className="text-[10px] font-mono text-status-error leading-none">
            {error}
          </span>
        ) : (
          <span className="text-[9px] font-mono uppercase tracking-[0.14em] text-text-muted leading-none">
            parallel
          </span>
        )}
      </div>

      <div className="flex items-stretch gap-3">
        {/* numeric readout on the left — large mono digit */}
        <div
          className={[
            "flex items-center justify-center w-16 bg-surface border rounded",
            error ? "border-status-error/60" : "border-border-default",
          ].join(" ")}
        >
          <span className="text-xl font-mono font-medium tabular-nums text-text-primary leading-none">
            {Number.isNaN(value) ? "—" : String(clamped).padStart(2, "0")}
          </span>
        </div>

        {/* tick-bar slider on the right */}
        <div className="flex-1 flex flex-col justify-center gap-1.5">
          {/* ticks */}
          <div className="relative h-5">
            {/* baseline */}
            <div className="absolute left-0 right-0 top-1/2 -translate-y-1/2 h-px bg-border-default" />
            {/* filled segment */}
            <div
              className="absolute left-0 top-1/2 -translate-y-1/2 h-px bg-accent"
              style={{ width: `${fillPct}%` }}
            />
            {/* ticks */}
            <div className="absolute inset-0 flex items-center justify-between">
              {Array.from({ length: 16 }).map((_, i) => {
                const active = i + 1 <= clamped;
                return (
                  <span
                    key={i}
                    className={[
                      "block w-px",
                      active ? "bg-accent" : "bg-border-emphasis",
                      i === 0 || i === 15 ? "h-4" : "h-2.5",
                    ].join(" ")}
                    aria-hidden
                  />
                );
              })}
            </div>
            {/* invisible native range on top for interaction */}
            <input
              type="range"
              min={1}
              max={16}
              step={1}
              value={clamped}
              onChange={(e) => onChange(Number(e.target.value))}
              aria-label="Workers"
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            />
          </div>
          {/* scale labels */}
          <div className="flex items-center justify-between text-[9px] font-mono tabular-nums text-text-muted leading-none select-none">
            <span>01</span>
            <span>08</span>
            <span>16</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ========================================================================= */
/* ConfigField — styled <select>                                              */
/* ========================================================================= */

function ConfigField({
  value,
  onChange,
  configs,
  loading,
  loadError,
  error,
}: {
  value: string;
  onChange: (name: string) => void;
  configs: ConfigSummary[];
  loading: boolean;
  loadError: string | null;
  error?: string;
}) {
  const summary = useMemo(
    () => configs.find((c) => c.name === value)?.summary ?? null,
    [configs, value],
  );

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-1.5">
          <span className="text-[9px] font-mono text-text-muted leading-none">
            [06]
          </span>
          <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-secondary leading-none">
            Engine Config
          </span>
        </div>
        {error ? (
          <span className="text-[10px] font-mono text-status-error leading-none">
            {error}
          </span>
        ) : loadError ? (
          <span className="text-[10px] font-mono text-status-error leading-none truncate max-w-[60%]">
            {loadError}
          </span>
        ) : loading ? (
          <span className="text-[9px] font-mono uppercase tracking-[0.14em] text-text-muted leading-none">
            loading…
          </span>
        ) : (
          <span className="text-[9px] font-mono uppercase tracking-[0.14em] text-text-muted leading-none">
            {configs.length.toString().padStart(2, "0")} available
          </span>
        )}
      </div>

      <div
        className={[
          "relative flex items-center bg-surface border rounded",
          "transition-colors duration-150 ease-out",
          error
            ? "border-status-error/60 focus-within:border-status-error"
            : "border-border-default focus-within:border-border-emphasis",
        ].join(" ")}
      >
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={loading || configs.length === 0}
          className={[
            "flex-1 min-w-0 appearance-none bg-transparent outline-none",
            "px-3 py-2 pr-8 text-sm font-mono text-text-primary",
            "disabled:text-text-muted disabled:cursor-not-allowed",
          ].join(" ")}
        >
          {configs.length === 0 && (
            <option value="" className="bg-surface text-text-muted">
              {loading ? "Loading…" : "No configs found"}
            </option>
          )}
          {configs.map((c) => (
            <option key={c.name} value={c.name} className="bg-surface text-text-primary">
              {c.name}
            </option>
          ))}
        </select>
        {/* caret */}
        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-text-muted text-[10px] leading-none">
          &#9662;
        </span>
      </div>

      {summary && (
        <p className="text-[10px] font-mono text-text-muted leading-snug truncate">
          {summary}
        </p>
      )}
    </div>
  );
}

/* ========================================================================= */
/* Spinner — simple CSS spinner, no library                                   */
/* ========================================================================= */

function Spinner() {
  return (
    <span
      className="inline-block w-3 h-3 border border-current border-t-transparent rounded-full animate-spin"
      aria-hidden
    />
  );
}
