import { useParametricStore } from "../../state/parametricStore";
import { api } from "../../api/client";
import type { ParametricRun } from "../../types/parametric";

export default function ParametricRunGrid() {
  const current = useParametricStore((s) => s.current);
  const availableParameters = useParametricStore((s) => s.availableParameters);

  if (!current) return null;

  const param = availableParameters.find(
    (p) => p.path === current.definition.parameter_path,
  );
  const scale = param?.display_scale ?? 1;
  const unit = param?.unit ?? "";

  const handleStop = async () => {
    try {
      await api.stopParametricStudy();
    } catch (err) {
      console.error(err);
    }
  };

  const doneCount = current.runs.filter((r) => r.status === "done").length;
  const totalCount = current.runs.length;

  const totalRpms =
    Math.round(
      (current.definition.sweep_rpm_end -
        current.definition.sweep_rpm_start) /
        current.definition.sweep_rpm_step,
    ) + 1;

  return (
    <div className="h-full flex flex-col bg-bg text-text-primary font-ui">
      <header className="flex items-center justify-between border-b border-border-default p-6">
        <div>
          <h1 className="text-lg font-semibold">{current.definition.name}</h1>
          <p className="text-sm text-text-muted mt-1">
            {param?.label ?? current.definition.parameter_path} ·{" "}
            <span className="font-mono">
              {doneCount} / {totalCount}
            </span>{" "}
            runs complete
          </p>
        </div>
        <button
          type="button"
          onClick={handleStop}
          className="px-4 py-2 text-xs uppercase tracking-wider border border-status-error text-status-error hover:bg-status-error hover:text-bg transition-colors"
        >
          Stop Study
        </button>
      </header>

      <div className="flex-1 overflow-auto p-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {current.runs.map((run, idx) => (
            <RunCard
              key={idx}
              run={run}
              displayValue={(run.parameter_value * scale).toFixed(3)}
              unit={unit}
              totalRpms={totalRpms}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function RunCard({
  run,
  displayValue,
  unit,
  totalRpms,
}: {
  run: ParametricRun;
  displayValue: string;
  unit: string;
  totalRpms: number;
}) {
  const completedRpms = run.sweep_results.length;
  const progress = totalRpms > 0 ? completedRpms / totalRpms : 0;

  const statusColor = {
    queued: "text-text-muted",
    running: "text-accent",
    done: "text-status-success",
    error: "text-status-error",
  }[run.status];

  // Tiny power sparkline using inline SVG
  const powers = run.sweep_results
    .map((p) => (typeof p.brake_power_hp === "number" ? p.brake_power_hp : 0))
    .filter((v) => Number.isFinite(v));
  const maxPower = powers.length ? Math.max(...powers) : 1;
  const minPower = powers.length ? Math.min(...powers) : 0;
  const range = Math.max(maxPower - minPower, 1);

  return (
    <div
      className={`border p-3 transition-colors ${
        run.status === "running"
          ? "border-accent bg-surface-raised"
          : "border-border-default bg-surface"
      }`}
    >
      <div className="flex items-baseline justify-between mb-2">
        <span className="font-mono text-sm">
          {displayValue}
          <span className="text-text-muted ml-1">{unit}</span>
        </span>
        <span
          className={`text-[10px] uppercase tracking-wider ${statusColor}`}
        >
          {run.status}
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-1 bg-border-default mb-2 relative">
        <div
          className="h-full bg-accent transition-all"
          style={{ width: `${progress * 100}%` }}
        />
      </div>

      {/* Sparkline */}
      <svg viewBox="0 0 100 30" className="w-full h-8 text-accent">
        {powers.length > 1 && (
          <polyline
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            points={powers
              .map((p, i) => {
                const x = (i / (powers.length - 1)) * 100;
                const y = 30 - ((p - minPower) / range) * 26 - 2;
                return `${x},${y}`;
              })
              .join(" ")}
          />
        )}
      </svg>

      <div className="flex justify-between text-[10px] font-mono text-text-muted mt-1">
        <span>
          {completedRpms}/{totalRpms} RPM
        </span>
        <span>{run.elapsed_seconds.toFixed(1)}s</span>
      </div>

      {run.error && (
        <div className="mt-2 text-[10px] text-status-error font-mono line-clamp-2">
          {run.error.split("\n")[0]}
        </div>
      )}
    </div>
  );
}
