import { useMemo, useState } from "react";
import { useParametricStore } from "../../state/parametricStore";
import { computeHeatmapData } from "../../state/parametricSelectors";

const METRIC_OPTIONS = [
  { key: "brake_power_hp", label: "Brake HP" },
  { key: "brake_torque_Nm", label: "Brake Torque" },
  { key: "volumetric_efficiency_atm", label: "VE (atm)" },
  { key: "plenum_pressure_bar", label: "Plenum P" },
];

/** Linear interpolation from blue (low) to orange (high). */
function colorFor(
  value: number | null,
  min: number,
  max: number,
): string {
  if (value === null) return "#1a1a1a";
  const t = (value - min) / Math.max(max - min, 1e-9);
  const hue = 200 - t * 180; // 200 blue → 20 orange
  const lightness = 35 + t * 25;
  return `hsl(${hue}, 75%, ${lightness}%)`;
}

export default function ParametricHeatmap() {
  const current = useParametricStore((s) => s.current);
  const availableParameters = useParametricStore((s) => s.availableParameters);
  const [metricKey, setMetricKey] = useState("brake_power_hp");
  const [expanded, setExpanded] = useState(true);

  const heatmapData = useMemo(() => {
    if (!current) return null;
    return computeHeatmapData(current, metricKey);
  }, [current, metricKey]);

  if (!current || !heatmapData) return null;

  const param = availableParameters.find(
    (p) => p.path === current.definition.parameter_path,
  );
  const scale = param?.display_scale ?? 1;
  const unit = param?.unit ?? "";

  // Flatten to find global min/max
  const flat = heatmapData.values
    .flat()
    .filter((v): v is number => v !== null && Number.isFinite(v));
  const min = flat.length ? Math.min(...flat) : 0;
  const max = flat.length ? Math.max(...flat) : 1;

  // For each RPM column, find the row index with the max value (the
  // "sweet spot" per RPM).
  const bestRowPerColumn: number[] = heatmapData.rpms.map((_, colIdx) => {
    let bestRow = -1;
    let bestVal = -Infinity;
    heatmapData.values.forEach((row, rowIdx) => {
      const v = row[colIdx];
      if (v !== null && v > bestVal) {
        bestVal = v;
        bestRow = rowIdx;
      }
    });
    return bestRow;
  });

  return (
    <div className="border border-border-default bg-surface">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 border-b border-border-default text-xs uppercase tracking-[0.18em] text-text-muted hover:text-text-primary"
      >
        <span>Heatmap: {METRIC_OPTIONS.find((m) => m.key === metricKey)?.label}</span>
        <span>{expanded ? "▼" : "▶"}</span>
      </button>

      {expanded && (
        <div className="p-4">
          <div className="mb-3">
            <label className="text-[10px] uppercase tracking-wider text-text-muted mr-2">
              Metric:
            </label>
            <select
              value={metricKey}
              onChange={(e) => setMetricKey(e.target.value)}
              className="bg-surface border border-border-default text-xs px-2 py-1"
            >
              {METRIC_OPTIONS.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>

          <div className="overflow-x-auto">
            <table className="border-collapse text-[10px] font-mono">
              <thead>
                <tr>
                  <th className="sticky left-0 bg-surface p-1 text-text-muted text-right">
                    {param?.label ?? "Value"}
                  </th>
                  {heatmapData.rpms.map((rpm) => (
                    <th
                      key={rpm}
                      className="p-1 text-text-muted font-normal"
                      style={{ minWidth: 36 }}
                    >
                      {Math.round(rpm)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {heatmapData.parameterValues.map((value, rowIdx) => (
                  <tr key={rowIdx}>
                    <td className="sticky left-0 bg-surface p-1 text-right text-text-muted pr-2">
                      {(value * scale).toFixed(3)} {unit}
                    </td>
                    {heatmapData.values[rowIdx].map((cellValue, colIdx) => {
                      const isBest = bestRowPerColumn[colIdx] === rowIdx;
                      return (
                        <td
                          key={colIdx}
                          className="p-0 text-center relative"
                          style={{
                            backgroundColor: colorFor(cellValue, min, max),
                            minWidth: 36,
                            height: 24,
                          }}
                          title={
                            cellValue === null
                              ? "—"
                              : cellValue.toFixed(1)
                          }
                        >
                          {isBest && (
                            <span className="absolute inset-0 flex items-center justify-center text-[8px] text-bg">
                              ●
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-3 flex items-center gap-3 text-[10px] font-mono text-text-muted">
            <span>{min.toFixed(1)}</span>
            <div
              className="flex-1 h-3 max-w-xs"
              style={{
                background:
                  "linear-gradient(to right, hsl(200,75%,35%), hsl(110,75%,48%), hsl(20,75%,60%))",
              }}
            />
            <span>{max.toFixed(1)}</span>
          </div>
        </div>
      )}
    </div>
  );
}
