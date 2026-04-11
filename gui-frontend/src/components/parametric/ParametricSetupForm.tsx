import { useEffect, useMemo, useState } from "react";
import { useParametricStore } from "../../state/parametricStore";
import { api, type ConfigSummary } from "../../api/client";
import type { Param } from "../../types/parametric";

interface FormState {
  name: string;
  config_name: string;
  parameter_path: string;
  value_start: string; // display-scaled strings
  value_end: string;
  value_step: string;
  sweep_rpm_start: string;
  sweep_rpm_end: string;
  sweep_rpm_step: string;
  sweep_n_cycles: string;
  n_workers: number;
}

const DEFAULTS: Omit<FormState, "parameter_path" | "config_name"> = {
  name: "",
  value_start: "",
  value_end: "",
  value_step: "",
  sweep_rpm_start: "3000",
  sweep_rpm_end: "15000",
  sweep_rpm_step: "500",
  sweep_n_cycles: "8",
  n_workers: 8,
};

const INPUT_CLS =
  "w-full bg-surface border border-border-default rounded px-2 py-1.5 text-sm outline-none focus:border-accent";
const INPUT_MONO_CLS =
  "w-full bg-surface border border-border-default rounded px-2 py-1.5 text-sm font-mono outline-none focus:border-accent";

export default function ParametricSetupForm() {
  const availableParameters = useParametricStore((s) => s.availableParameters);
  const [configs, setConfigs] = useState<ConfigSummary[]>([]);
  const [form, setForm] = useState<FormState>({
    ...DEFAULTS,
    config_name: "cbr600rr.json",
    parameter_path: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api
      .listConfigs()
      .then(setConfigs)
      .catch((err) => setError(String(err)));
  }, []);

  // When parameter selection changes, auto-populate the value range from
  // the parameter's default_range, converted through display_scale.
  useEffect(() => {
    if (!form.parameter_path) return;
    const param = availableParameters.find(
      (p) => p.path === form.parameter_path,
    );
    if (!param) return;
    const [start, end, step] = param.default_range;
    const scale = param.display_scale;
    setForm((f) => ({
      ...f,
      value_start: (start * scale).toString(),
      value_end: (end * scale).toString(),
      value_step: (step * scale).toString(),
      name: f.name || `${param.label} sweep`,
    }));
  }, [form.parameter_path, availableParameters]);

  const selectedParam = useMemo(
    () => availableParameters.find((p) => p.path === form.parameter_path),
    [form.parameter_path, availableParameters],
  );

  // Group parameters by category
  const paramsByCategory = useMemo(() => {
    const map: Record<string, Param[]> = {};
    for (const p of availableParameters) {
      (map[p.category] ||= []).push(p);
    }
    return map;
  }, [availableParameters]);

  const parameterValueCount = useMemo(() => {
    const vs = parseFloat(form.value_start);
    const ve = parseFloat(form.value_end);
    const step = parseFloat(form.value_step);
    if (!Number.isFinite(vs) || !Number.isFinite(ve) || !Number.isFinite(step))
      return 0;
    if (step <= 0 || ve <= vs) return 0;
    return Math.round((ve - vs) / step) + 1;
  }, [form.value_start, form.value_end, form.value_step]);

  const rpmPointCount = useMemo(() => {
    const rs = parseFloat(form.sweep_rpm_start);
    const re = parseFloat(form.sweep_rpm_end);
    const step = parseFloat(form.sweep_rpm_step);
    if (!Number.isFinite(rs) || !Number.isFinite(re) || !Number.isFinite(step))
      return 0;
    if (step <= 0 || re <= rs) return 0;
    return Math.round((re - rs) / step) + 1;
  }, [form.sweep_rpm_start, form.sweep_rpm_end, form.sweep_rpm_step]);

  const totalSimulations = parameterValueCount * rpmPointCount;

  const canSubmit =
    selectedParam !== undefined &&
    parameterValueCount > 0 &&
    rpmPointCount > 0 &&
    form.name.trim().length > 0 &&
    !submitting;

  const handleSubmit = async () => {
    if (!selectedParam) return;
    setSubmitting(true);
    setError(null);
    try {
      const scale = selectedParam.display_scale;
      await api.startParametricStudy({
        name: form.name.trim(),
        config_name: form.config_name,
        parameter_path: form.parameter_path,
        value_start: parseFloat(form.value_start) / scale,
        value_end: parseFloat(form.value_end) / scale,
        value_step: parseFloat(form.value_step) / scale,
        sweep_rpm_start: parseFloat(form.sweep_rpm_start),
        sweep_rpm_end: parseFloat(form.sweep_rpm_end),
        sweep_rpm_step: parseFloat(form.sweep_rpm_step),
        sweep_n_cycles: parseInt(form.sweep_n_cycles, 10),
        n_workers: form.n_workers,
      });
      // The WebSocket will push parametric_study_start which flips the
      // store to running — this component will unmount.
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  return (
    <div className="flex h-full overflow-auto bg-bg text-text-primary font-ui">
      <div className="flex-1 p-8 max-w-3xl">
        <header className="mb-8">
          <h1 className="text-lg font-semibold tracking-wide">
            Parametric Study
          </h1>
          <p className="text-sm text-text-muted mt-1">
            Sweep one engine-design parameter across a range and compare
            full RPM sweeps for each value.
          </p>
        </header>

        <div className="space-y-5">
          <Field index="01" label="Name">
            <input
              className={INPUT_CLS}
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="e.g. Intake runner length sweep"
            />
          </Field>

          <Field index="02" label="Engine Config">
            <select
              className={INPUT_CLS}
              value={form.config_name}
              onChange={(e) =>
                setForm((f) => ({ ...f, config_name: e.target.value }))
              }
            >
              {configs.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
          </Field>

          <Field index="03" label="Parameter">
            <select
              className={INPUT_CLS}
              value={form.parameter_path}
              onChange={(e) =>
                setForm((f) => ({ ...f, parameter_path: e.target.value }))
              }
            >
              <option value="">— select a parameter —</option>
              {Object.entries(paramsByCategory).map(([category, params]) => (
                <optgroup key={category} label={category}>
                  {params.map((p) => (
                    <option key={p.path} value={p.path}>
                      {p.label} {p.unit ? `(${p.unit})` : ""}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </Field>

          {selectedParam && (
            <div className="grid grid-cols-3 gap-3">
              <Field
                index="04"
                label={`Start${selectedParam.unit ? ` (${selectedParam.unit})` : ""}`}
              >
                <input
                  className={INPUT_MONO_CLS}
                  value={form.value_start}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, value_start: e.target.value }))
                  }
                />
              </Field>
              <Field
                index="05"
                label={`End${selectedParam.unit ? ` (${selectedParam.unit})` : ""}`}
              >
                <input
                  className={INPUT_MONO_CLS}
                  value={form.value_end}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, value_end: e.target.value }))
                  }
                />
              </Field>
              <Field
                index="06"
                label={`Step${selectedParam.unit ? ` (${selectedParam.unit})` : ""}`}
              >
                <input
                  className={INPUT_MONO_CLS}
                  value={form.value_step}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, value_step: e.target.value }))
                  }
                />
              </Field>
            </div>
          )}

          <div className="grid grid-cols-3 gap-3">
            <Field index="07" label="RPM Start">
              <input
                className={INPUT_MONO_CLS}
                value={form.sweep_rpm_start}
                onChange={(e) =>
                  setForm((f) => ({ ...f, sweep_rpm_start: e.target.value }))
                }
              />
            </Field>
            <Field index="08" label="RPM End">
              <input
                className={INPUT_MONO_CLS}
                value={form.sweep_rpm_end}
                onChange={(e) =>
                  setForm((f) => ({ ...f, sweep_rpm_end: e.target.value }))
                }
              />
            </Field>
            <Field index="09" label="RPM Step">
              <input
                className={INPUT_MONO_CLS}
                value={form.sweep_rpm_step}
                onChange={(e) =>
                  setForm((f) => ({ ...f, sweep_rpm_step: e.target.value }))
                }
              />
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field index="10" label="Cycles per RPM">
              <input
                className={INPUT_MONO_CLS}
                value={form.sweep_n_cycles}
                onChange={(e) =>
                  setForm((f) => ({ ...f, sweep_n_cycles: e.target.value }))
                }
              />
            </Field>
            <Field index="11" label="Workers">
              <input
                type="number"
                min={1}
                max={16}
                className={INPUT_MONO_CLS}
                value={form.n_workers}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    n_workers: Math.max(
                      1,
                      Math.min(16, parseInt(e.target.value, 10) || 1),
                    ),
                  }))
                }
              />
            </Field>
          </div>

          {error && (
            <div className="text-sm text-status-error border border-status-error p-3">
              {error}
            </div>
          )}

          <div className="flex items-center gap-4 pt-4">
            <button
              type="button"
              disabled={!canSubmit}
              onClick={handleSubmit}
              className="px-5 py-2 text-sm uppercase tracking-wider border border-accent text-accent hover:bg-accent hover:text-bg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {submitting ? "Starting..." : "Start Study"}
            </button>
          </div>
        </div>
      </div>

      {/* Live readout panel */}
      <aside className="w-72 border-l border-border-default bg-surface p-6 text-sm font-ui">
        <h2 className="text-xs uppercase tracking-[0.18em] text-text-muted mb-4">
          Study Plan
        </h2>
        <dl className="space-y-3 font-mono">
          <Stat label="Parameter Values" value={String(parameterValueCount)} />
          <Stat label="RPM Points" value={String(rpmPointCount)} />
          <Stat
            label="Total Simulations"
            value={String(totalSimulations)}
            emphasis
          />
        </dl>
        {selectedParam && (
          <div className="mt-6 text-xs text-text-muted">
            <div className="uppercase tracking-wider mb-1">Bounds</div>
            <div className="font-mono">
              min: {selectedParam.min_allowed ?? "—"}
              <br />
              max: {selectedParam.max_allowed ?? "—"}
              <br />
              <span className="text-text-muted/70">
                (storage units, unscaled)
              </span>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

function Field({
  index,
  label,
  children,
}: {
  index: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <div className="flex items-baseline gap-2 mb-1.5">
        <span className="text-[9px] font-mono text-text-muted">[{index}]</span>
        <span className="text-[11px] uppercase tracking-[0.14em] text-text-muted">
          {label}
        </span>
      </div>
      {children}
    </label>
  );
}

function Stat({
  label,
  value,
  emphasis = false,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
}) {
  return (
    <div className="flex justify-between items-baseline">
      <span className="text-[11px] uppercase tracking-wider text-text-muted">
        {label}
      </span>
      <span
        className={
          emphasis ? "text-accent font-semibold" : "text-text-primary"
        }
      >
        {value}
      </span>
    </div>
  );
}
