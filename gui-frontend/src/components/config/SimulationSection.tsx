import { useConfigStore } from "../../state/configStore";
import { Accordion } from "../forms/Accordion";
import { NumericField } from "../forms/NumericField";

export default function SimulationSection() {
  const draft = useConfigStore((s) => s.draft);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  if (draft === null) return null;
  const s = draft.simulation;

  return (
    <Accordion id="simulation" index="12" label="Simulation">
      <div className="grid grid-cols-3 gap-3">
        <NumericField
          index="01"
          label="RPM Start"
          unit="rpm"
          value={s.rpm_start}
          onChange={(v) => setField("simulation.rpm_start", v)}
          error={fieldErrors["simulation.rpm_start"]}
          step={100}
        />
        <NumericField
          index="02"
          label="RPM End"
          unit="rpm"
          value={s.rpm_end}
          onChange={(v) => setField("simulation.rpm_end", v)}
          error={fieldErrors["simulation.rpm_end"]}
          step={100}
        />
        <NumericField
          index="03"
          label="RPM Step"
          unit="rpm"
          value={s.rpm_step}
          onChange={(v) => setField("simulation.rpm_step", v)}
          error={fieldErrors["simulation.rpm_step"]}
          step={50}
        />
        <NumericField
          index="04"
          label="N Cycles"
          unit="—"
          value={s.n_cycles}
          onChange={(v) => setField("simulation.n_cycles", v)}
          error={fieldErrors["simulation.n_cycles"]}
          step={1}
          min={1}
        />
        <NumericField
          index="05"
          label="CFL Number"
          unit="—"
          value={s.cfl_number}
          onChange={(v) => setField("simulation.cfl_number", v)}
          error={fieldErrors["simulation.cfl_number"]}
          step={0.05}
        />
        <NumericField
          index="06"
          label="Convergence Tol"
          unit="—"
          value={s.convergence_tolerance}
          onChange={(v) => setField("simulation.convergence_tolerance", v)}
          error={fieldErrors["simulation.convergence_tolerance"]}
          step={0.001}
        />
        <NumericField
          index="07"
          label="Crank Step Max"
          unit="deg"
          value={s.crank_step_max}
          onChange={(v) => setField("simulation.crank_step_max", v)}
          error={fieldErrors["simulation.crank_step_max"]}
          step={0.1}
        />
        <NumericField
          index="08"
          label="Artificial Viscosity"
          unit="—"
          value={s.artificial_viscosity}
          onChange={(v) => setField("simulation.artificial_viscosity", v)}
          error={fieldErrors["simulation.artificial_viscosity"]}
          step={0.01}
        />
      </div>
    </Accordion>
  );
}
