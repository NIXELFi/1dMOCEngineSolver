import { useDynoStore } from "../../state/dynoStore";
import GaugeCard from "./GaugeCard";

/** Gauge definition for declarative layout. */
interface GaugeDef {
  field: string;
  label: string;
  unit: string;
  precision: number;
  /** Scale factor applied to the raw value before display. */
  scale?: number;
}

const PRIMARY_GAUGES: GaugeDef[] = [
  { field: "rpm", label: "RPM", unit: "RPM", precision: 0 },
  { field: "brake_power_hp", label: "Brake Power", unit: "hp", precision: 1 },
  { field: "brake_torque_Nm", label: "Brake Torque", unit: "Nm", precision: 1 },
];

const INDICATED_WHEEL_GAUGES: GaugeDef[] = [
  { field: "indicated_power_hp", label: "Indicated Power", unit: "hp", precision: 1 },
  { field: "indicated_torque_Nm", label: "Indicated Torque", unit: "Nm", precision: 1 },
  { field: "wheel_power_hp", label: "Wheel Power", unit: "hp", precision: 1 },
  { field: "wheel_torque_Nm", label: "Wheel Torque", unit: "Nm", precision: 1 },
];

const EFFICIENCY_GAUGES: GaugeDef[] = [
  { field: "volumetric_efficiency_atm", label: "VE (Atm)", unit: "%", precision: 1, scale: 100 },
  { field: "volumetric_efficiency_plenum", label: "VE (Plenum)", unit: "%", precision: 1, scale: 100 },
  { field: "drivetrain_efficiency", label: "Drivetrain Eff.", unit: "%", precision: 1, scale: 100 },
];

const MEP_GAUGES: GaugeDef[] = [
  { field: "imep_bar", label: "IMEP", unit: "bar", precision: 2 },
  { field: "bmep_bar", label: "BMEP", unit: "bar", precision: 2 },
  { field: "fmep_bar", label: "FMEP", unit: "bar", precision: 2 },
];

const INTAKE_GAUGES: GaugeDef[] = [
  { field: "plenum_pressure_bar", label: "Plenum Pressure", unit: "bar", precision: 3 },
  { field: "restrictor_mdot", label: "Restrictor Flow", unit: "g/s", precision: 2, scale: 1000 },
  { field: "intake_mass_per_cycle_g", label: "Intake Mass/Cycle", unit: "g", precision: 3 },
];

/** Render a row of gauge cards from a gauge definition array. */
function GaugeRow({
  gauges,
  primary = false,
}: {
  gauges: GaugeDef[];
  primary?: boolean;
}) {
  const interpolated = useDynoStore((s) => s.interpolated);
  const fieldRanges = useDynoStore((s) => s.fieldRanges);

  return (
    <>
      {gauges.map((g) => {
        const raw = interpolated?.[g.field as keyof typeof interpolated];
        const rawNum = typeof raw === "number" ? raw : 0;
        const scale = g.scale ?? 1;
        const value = rawNum * scale;
        const range = fieldRanges[g.field];
        const min = (range?.min ?? 0) * scale;
        const max = (range?.max ?? 0) * scale;

        return (
          <GaugeCard
            key={g.field}
            label={g.label}
            value={value}
            unit={g.unit}
            min={min}
            max={max}
            precision={g.precision}
            primary={primary}
          />
        );
      })}
    </>
  );
}

export default function GaugePanel() {
  const interpolated = useDynoStore((s) => s.interpolated);

  if (!interpolated) return null;

  const choked = interpolated.restrictor_choked ?? false;

  return (
    <div className="flex flex-col gap-2">
      {/* Primary row — 3 large gauges */}
      <div className="grid grid-cols-3 gap-2">
        <GaugeRow gauges={PRIMARY_GAUGES} primary />
      </div>

      {/* Indicated & Wheel — 4 gauges */}
      <div className="grid grid-cols-4 gap-2">
        <GaugeRow gauges={INDICATED_WHEEL_GAUGES} />
      </div>

      {/* Efficiency — 3 gauges */}
      <div className="grid grid-cols-3 gap-2">
        <GaugeRow gauges={EFFICIENCY_GAUGES} />
      </div>

      {/* MEP — 3 gauges */}
      <div className="grid grid-cols-3 gap-2">
        <GaugeRow gauges={MEP_GAUGES} />
      </div>

      {/* Intake — 3 gauges + choked indicator */}
      <div className="grid grid-cols-4 gap-2">
        <GaugeRow gauges={INTAKE_GAUGES} />

        {/* Choked indicator */}
        <div className="flex flex-col items-center justify-center gap-1.5 bg-surface-raised border border-border-default rounded px-3 py-2 font-ui">
          <span className="text-[9px] font-semibold uppercase tracking-[0.18em] text-text-muted leading-none">
            Restrictor
          </span>
          <div className="flex items-center gap-2">
            <span
              className={[
                "inline-block w-2 h-2 rounded-full transition-colors duration-150",
                choked ? "bg-accent" : "bg-text-muted opacity-40",
              ].join(" ")}
            />
            <span
              className={[
                "text-[10px] font-mono font-semibold uppercase tracking-[0.14em] leading-none",
                choked ? "text-accent" : "text-text-muted",
              ].join(" ")}
            >
              {choked ? "Choked" : "Unchoked"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
