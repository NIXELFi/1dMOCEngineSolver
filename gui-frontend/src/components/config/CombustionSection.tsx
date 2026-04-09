import { useConfigStore } from "../../state/configStore";
import { Accordion } from "../forms/Accordion";
import { NumericField } from "../forms/NumericField";

export default function CombustionSection() {
  const draft = useConfigStore((s) => s.draft);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  if (draft === null) return null;
  const c = draft.combustion;

  return (
    <Accordion id="combustion" index="09" label="Combustion">
      <div className="grid grid-cols-3 gap-3">
        <NumericField
          index="01"
          label="Wiebe a"
          unit="—"
          value={c.wiebe_a}
          onChange={(v) => setField("combustion.wiebe_a", v)}
          error={fieldErrors["combustion.wiebe_a"]}
          step={0.1}
        />
        <NumericField
          index="02"
          label="Wiebe m"
          unit="—"
          value={c.wiebe_m}
          onChange={(v) => setField("combustion.wiebe_m", v)}
          error={fieldErrors["combustion.wiebe_m"]}
          step={0.1}
        />
        <NumericField
          index="03"
          label="Combustion Duration"
          unit="deg"
          value={c.combustion_duration}
          onChange={(v) => setField("combustion.combustion_duration", v)}
          error={fieldErrors["combustion.combustion_duration"]}
          step={1}
        />
        <NumericField
          index="04"
          label="Spark Advance"
          unit="deg BTDC"
          value={c.spark_advance}
          onChange={(v) => setField("combustion.spark_advance", v)}
          error={fieldErrors["combustion.spark_advance"]}
          step={0.5}
        />
        <NumericField
          index="05"
          label="Ignition Delay"
          unit="deg"
          value={c.ignition_delay}
          onChange={(v) => setField("combustion.ignition_delay", v)}
          error={fieldErrors["combustion.ignition_delay"]}
          step={0.5}
        />
        <NumericField
          index="06"
          label="Combustion Efficiency"
          unit="—"
          value={c.combustion_efficiency}
          onChange={(v) => setField("combustion.combustion_efficiency", v)}
          error={fieldErrors["combustion.combustion_efficiency"]}
          step={0.01}
        />
        <NumericField
          index="07"
          label="LHV"
          unit="MJ/kg"
          value={c.q_lhv}
          onChange={(v) => setField("combustion.q_lhv", v)}
          error={fieldErrors["combustion.q_lhv"]}
          displayScale={1e-6}
          step={0.1}
        />
        <NumericField
          index="08"
          label="AFR Stoich"
          unit="—"
          value={c.afr_stoich}
          onChange={(v) => setField("combustion.afr_stoich", v)}
          error={fieldErrors["combustion.afr_stoich"]}
          step={0.1}
        />
        <NumericField
          index="09"
          label="AFR Target"
          unit="—"
          value={c.afr_target}
          onChange={(v) => setField("combustion.afr_target", v)}
          error={fieldErrors["combustion.afr_target"]}
          step={0.1}
        />
      </div>
    </Accordion>
  );
}
