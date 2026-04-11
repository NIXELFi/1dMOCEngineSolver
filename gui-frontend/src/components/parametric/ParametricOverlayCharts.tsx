import { useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useParametricStore } from "../../state/parametricStore";
import type { ParametricRun, PerfDict } from "../../types/parametric";

interface ChartSpec {
  title: string;
  dataKey: keyof PerfDict | string;
  unit: string;
}

const CHARTS: ChartSpec[] = [
  { title: "Brake Power", dataKey: "brake_power_hp", unit: "hp" },
  { title: "Brake Torque", dataKey: "brake_torque_Nm", unit: "Nm" },
  { title: "Volumetric Eff (atm)", dataKey: "volumetric_efficiency_atm", unit: "" },
  { title: "Plenum Pressure", dataKey: "plenum_pressure_bar", unit: "bar" },
];

/** Generate N distinct HSL colors (cool → warm) for the run overlays. */
function runColor(index: number, total: number): string {
  if (total <= 1) return "hsl(30, 90%, 60%)";
  const hue = 200 - (index / (total - 1)) * 180; // 200 (blue) → 20 (orange)
  return `hsl(${hue}, 75%, 60%)`;
}

interface ChartPoint {
  rpm: number;
  [runKey: string]: number | null;
}

function buildChartData(
  runs: ParametricRun[],
  selectedIndices: Set<number>,
  dataKey: string,
): ChartPoint[] {
  // Collect union of RPMs
  const rpmSet = new Set<number>();
  for (const run of runs) {
    for (const perf of run.sweep_results) {
      rpmSet.add(perf.rpm);
    }
  }
  const rpms = Array.from(rpmSet).sort((a, b) => a - b);

  return rpms.map((rpm) => {
    const point: ChartPoint = { rpm };
    runs.forEach((run, idx) => {
      if (!selectedIndices.has(idx)) {
        point[`run_${idx}`] = null;
        return;
      }
      const perf = run.sweep_results.find((p) => p.rpm === rpm);
      const value = perf ? (perf as Record<string, unknown>)[dataKey] : null;
      point[`run_${idx}`] =
        typeof value === "number" && Number.isFinite(value) ? value : null;
    });
    return point;
  });
}

export default function ParametricOverlayCharts() {
  const current = useParametricStore((s) => s.current);
  const selectedIndices = useParametricStore((s) => s.selectedRunIndices);
  const availableParameters = useParametricStore((s) => s.availableParameters);
  const toggleRunSelected = useParametricStore((s) => s.toggleRunSelected);

  if (!current) return null;

  const param = availableParameters.find(
    (p) => p.path === current.definition.parameter_path,
  );
  const scale = param?.display_scale ?? 1;
  const unit = param?.unit ?? "";

  return (
    <div>
      <div className="flex gap-4">
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-4">
          {CHARTS.map((spec) => (
            <OverlayChart
              key={spec.title}
              spec={spec}
              runs={current.runs}
              selectedIndices={selectedIndices}
            />
          ))}
        </div>

        {/* Legend */}
        <aside className="w-48 shrink-0">
          <div className="text-[10px] uppercase tracking-wider text-text-muted mb-2">
            Runs
          </div>
          <div className="space-y-1">
            {current.runs.map((run, idx) => {
              const isSelected = selectedIndices.has(idx);
              return (
                <button
                  key={idx}
                  type="button"
                  onClick={() => toggleRunSelected(idx)}
                  className={`flex items-center gap-2 w-full text-left px-2 py-1 text-xs font-mono transition-colors ${
                    isSelected
                      ? "text-text-primary"
                      : "text-text-muted opacity-40"
                  }`}
                >
                  <span
                    className="w-3 h-3 border border-border-default"
                    style={{
                      backgroundColor: isSelected
                        ? runColor(idx, current.runs.length)
                        : "transparent",
                    }}
                  />
                  <span>
                    {(run.parameter_value * scale).toFixed(3)} {unit}
                  </span>
                </button>
              );
            })}
          </div>
        </aside>
      </div>
    </div>
  );
}

function OverlayChart({
  spec,
  runs,
  selectedIndices,
}: {
  spec: ChartSpec;
  runs: ParametricRun[];
  selectedIndices: Set<number>;
}) {
  const data = useMemo(
    () => buildChartData(runs, selectedIndices, String(spec.dataKey)),
    [runs, selectedIndices, spec.dataKey],
  );

  return (
    <div className="border border-border-default bg-surface p-3">
      <h3 className="text-xs uppercase tracking-wider text-text-muted mb-2">
        {spec.title}
        {spec.unit && (
          <span className="text-text-muted/60 ml-1">({spec.unit})</span>
        )}
      </h3>
      <div style={{ width: "100%", height: 220 }}>
        <ResponsiveContainer>
          <LineChart data={data}>
            <CartesianGrid stroke="#333" strokeDasharray="3 3" />
            <XAxis
              dataKey="rpm"
              stroke="#888"
              tick={{ fontSize: 10, fontFamily: "monospace" }}
            />
            <YAxis
              stroke="#888"
              tick={{ fontSize: 10, fontFamily: "monospace" }}
            />
            <Tooltip
              contentStyle={{
                background: "#111",
                border: "1px solid #333",
                fontFamily: "monospace",
                fontSize: 11,
              }}
            />
            {runs.map((_, idx) => {
              if (!selectedIndices.has(idx)) return null;
              return (
                <Line
                  key={idx}
                  type="monotone"
                  dataKey={`run_${idx}`}
                  stroke={runColor(idx, runs.length)}
                  strokeWidth={1.5}
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
              );
            })}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
