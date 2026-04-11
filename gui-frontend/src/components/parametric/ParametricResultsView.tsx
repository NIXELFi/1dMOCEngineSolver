import { useParametricStore } from "../../state/parametricStore";
import type { ObjectiveKey } from "../../types/parametric";
import ParametricOverlayCharts from "./ParametricOverlayCharts";
import ParametricComparisonTable from "./ParametricComparisonTable";
import ParametricHeatmap from "./ParametricHeatmap";

const OBJECTIVES: { key: ObjectiveKey; label: string }[] = [
  { key: "peak_power", label: "Peak HP" },
  { key: "peak_torque", label: "Peak Torque" },
  { key: "torque_area", label: "Torque Area" },
  { key: "power_at_rpm", label: "HP @ RPM" },
  { key: "torque_at_rpm", label: "Torque @ RPM" },
];

export default function ParametricResultsView() {
  const current = useParametricStore((s) => s.current);
  const selectedObjective = useParametricStore((s) => s.selectedObjective);
  const objectiveRpm = useParametricStore((s) => s.objectiveRpm);
  const objectiveRpmWindow = useParametricStore((s) => s.objectiveRpmWindow);
  const setSelectedObjective = useParametricStore(
    (s) => s.setSelectedObjective,
  );
  const setObjectiveRpm = useParametricStore((s) => s.setObjectiveRpm);
  const setObjectiveRpmWindow = useParametricStore(
    (s) => s.setObjectiveRpmWindow,
  );
  const selectAllRuns = useParametricStore((s) => s.selectAllRuns);
  const clearSelectedRuns = useParametricStore((s) => s.clearSelectedRuns);
  const clearCurrent = useParametricStore((s) => s.clearCurrent);

  if (!current) return null;

  const needsRpm =
    selectedObjective === "power_at_rpm" ||
    selectedObjective === "torque_at_rpm";
  const needsWindow = selectedObjective === "torque_area";

  return (
    <div className="h-full overflow-auto bg-bg text-text-primary font-ui">
      <header className="sticky top-0 bg-bg border-b border-border-default px-6 py-4 z-10">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-lg font-semibold">{current.definition.name}</h1>
            <p className="text-xs text-text-muted mt-0.5 font-mono">
              {current.definition.parameter_path} · {current.runs.length} runs
              · status: {current.status}
            </p>
          </div>
          <button
            type="button"
            onClick={clearCurrent}
            className="px-3 py-1.5 text-xs uppercase tracking-wider border border-border-default hover:border-accent hover:text-accent"
          >
            New Study
          </button>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-[10px] uppercase tracking-wider text-text-muted">
            Objective:
          </span>
          {OBJECTIVES.map((obj) => (
            <button
              key={obj.key}
              type="button"
              onClick={() => setSelectedObjective(obj.key)}
              className={`px-3 py-1 text-xs uppercase tracking-wider border transition-colors ${
                selectedObjective === obj.key
                  ? "border-accent text-accent bg-surface-raised"
                  : "border-border-default text-text-muted hover:text-text-primary"
              }`}
            >
              {obj.label}
            </button>
          ))}

          {needsRpm && (
            <label className="flex items-center gap-2 ml-4">
              <span className="text-[10px] uppercase tracking-wider text-text-muted">
                RPM:
              </span>
              <input
                type="number"
                className="w-24 px-2 py-1 bg-surface border border-border-default text-sm font-mono"
                value={objectiveRpm}
                onChange={(e) => setObjectiveRpm(parseFloat(e.target.value))}
              />
            </label>
          )}

          {needsWindow && (
            <div className="flex items-center gap-2 ml-4">
              <span className="text-[10px] uppercase tracking-wider text-text-muted">
                Window:
              </span>
              <input
                type="number"
                className="w-24 px-2 py-1 bg-surface border border-border-default text-sm font-mono"
                value={objectiveRpmWindow[0]}
                onChange={(e) =>
                  setObjectiveRpmWindow([
                    parseFloat(e.target.value),
                    objectiveRpmWindow[1],
                  ])
                }
              />
              <span className="text-text-muted">–</span>
              <input
                type="number"
                className="w-24 px-2 py-1 bg-surface border border-border-default text-sm font-mono"
                value={objectiveRpmWindow[1]}
                onChange={(e) =>
                  setObjectiveRpmWindow([
                    objectiveRpmWindow[0],
                    parseFloat(e.target.value),
                  ])
                }
              />
            </div>
          )}

          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={selectAllRuns}
              className="text-xs text-text-muted hover:text-accent uppercase tracking-wider"
            >
              Show All
            </button>
            <span className="text-text-muted">·</span>
            <button
              type="button"
              onClick={clearSelectedRuns}
              className="text-xs text-text-muted hover:text-accent uppercase tracking-wider"
            >
              Hide All
            </button>
          </div>
        </div>
      </header>

      <div className="p-6 space-y-6">
        <ParametricOverlayCharts />
        <ParametricComparisonTable />
        <ParametricHeatmap />
      </div>
    </div>
  );
}
