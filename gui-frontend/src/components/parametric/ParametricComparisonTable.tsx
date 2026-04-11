import { useMemo } from "react";
import { useParametricStore } from "../../state/parametricStore";
import { computeComparisonTable } from "../../state/parametricSelectors";
import type { ObjectiveKey } from "../../types/parametric";

const OBJECTIVE_COLUMN: Record<ObjectiveKey, string> = {
  peak_power: "peak_power_hp",
  peak_torque: "peak_torque_Nm",
  torque_area: "torque_area",
  power_at_rpm: "power_at_rpm",
  torque_at_rpm: "torque_at_rpm",
};

function fmt(v: number | null, decimals = 1): string {
  if (v === null || !Number.isFinite(v)) return "—";
  return v.toFixed(decimals);
}

export default function ParametricComparisonTable() {
  const current = useParametricStore((s) => s.current);
  const selectedObjective = useParametricStore((s) => s.selectedObjective);
  const objectiveRpm = useParametricStore((s) => s.objectiveRpm);
  const objectiveRpmWindow = useParametricStore((s) => s.objectiveRpmWindow);
  const availableParameters = useParametricStore((s) => s.availableParameters);
  const setHighlightedRun = useParametricStore((s) => s.setHighlightedRun);
  const highlightedRunIndex = useParametricStore((s) => s.highlightedRunIndex);

  const rows = useMemo(() => {
    if (!current) return [];
    return computeComparisonTable(
      current,
      selectedObjective,
      objectiveRpm,
      objectiveRpmWindow,
    );
  }, [current, selectedObjective, objectiveRpm, objectiveRpmWindow]);

  if (!current) return null;

  const param = availableParameters.find(
    (p) => p.path === current.definition.parameter_path,
  );
  const scale = param?.display_scale ?? 1;
  const unit = param?.unit ?? "";
  const objectiveCol = OBJECTIVE_COLUMN[selectedObjective];

  return (
    <div className="border border-border-default bg-surface">
      <div className="px-4 py-3 border-b border-border-default flex items-center justify-between">
        <h2 className="text-xs uppercase tracking-[0.18em] text-text-muted">
          Comparison Table
        </h2>
        <span className="text-[10px] text-text-muted font-mono">
          ranked by {selectedObjective.replace("_", " ")}
        </span>
      </div>
      <table className="w-full text-xs font-mono">
        <thead>
          <tr className="border-b border-border-default text-text-muted">
            <Th>Rank</Th>
            <Th>Value</Th>
            <Th highlight={objectiveCol === "peak_power_hp"}>Peak HP (rpm)</Th>
            <Th highlight={objectiveCol === "peak_torque_Nm"}>
              Peak Torque (rpm)
            </Th>
            <Th highlight={objectiveCol === "torque_area"}>Torque Area</Th>
            <Th highlight={objectiveCol === "power_at_rpm"}>HP @ RPM</Th>
            <Th highlight={objectiveCol === "torque_at_rpm"}>Torque @ RPM</Th>
            <Th>VE peak</Th>
            <Th>Status</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isHighlighted = highlightedRunIndex === row.index;
            return (
              <tr
                key={row.index}
                onMouseEnter={() => setHighlightedRun(row.index)}
                onMouseLeave={() => setHighlightedRun(null)}
                className={`border-b border-border-default/30 cursor-pointer ${
                  isHighlighted
                    ? "bg-surface-raised"
                    : row.isBest
                      ? "bg-accent/5"
                      : ""
                }`}
              >
                <Td>
                  {row.rank !== null ? (
                    row.isBest ? (
                      <span className="text-accent font-semibold">
                        1
                      </span>
                    ) : (
                      <span>{row.rank}</span>
                    )
                  ) : (
                    <span className="text-text-muted">—</span>
                  )}
                </Td>
                <Td>
                  {(row.parameter_value * scale).toFixed(3)} {unit}
                </Td>
                <Td highlight={objectiveCol === "peak_power_hp"}>
                  {fmt(row.metrics.peak_power_hp)} (
                  {fmt(row.metrics.peak_power_rpm, 0)})
                </Td>
                <Td highlight={objectiveCol === "peak_torque_Nm"}>
                  {fmt(row.metrics.peak_torque_Nm)} (
                  {fmt(row.metrics.peak_torque_rpm, 0)})
                </Td>
                <Td highlight={objectiveCol === "torque_area"}>
                  {fmt(row.metrics.torque_area, 0)}
                </Td>
                <Td highlight={objectiveCol === "power_at_rpm"}>
                  {fmt(row.metrics.power_at_rpm)}
                </Td>
                <Td highlight={objectiveCol === "torque_at_rpm"}>
                  {fmt(row.metrics.torque_at_rpm)}
                </Td>
                <Td>{fmt(row.metrics.ve_peak, 2)}</Td>
                <Td>
                  <span
                    className={
                      row.status === "done"
                        ? "text-status-success"
                        : row.status === "error"
                          ? "text-status-error"
                          : "text-text-muted"
                    }
                  >
                    {row.status}
                  </span>
                </Td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {rows.some((r) => r.error) && (
        <div className="p-3 text-[10px] text-status-error font-mono border-t border-border-default">
          {rows
            .filter((r) => r.error)
            .map((r) => (
              <div key={r.index}>
                value {(r.parameter_value * scale).toFixed(3)} {unit}:{" "}
                {r.error?.split("\n")[0]}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

function Th({
  children,
  highlight = false,
}: {
  children: React.ReactNode;
  highlight?: boolean;
}) {
  return (
    <th
      className={`text-left px-3 py-2 text-[10px] uppercase tracking-wider ${
        highlight ? "text-accent" : ""
      }`}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  highlight = false,
}: {
  children: React.ReactNode;
  highlight?: boolean;
}) {
  return (
    <td className={`px-3 py-2 ${highlight ? "font-semibold" : ""}`}>
      {children}
    </td>
  );
}
