import { useConfigStore } from "../../state/configStore";
import { Accordion } from "../forms/Accordion";
import { NumericField } from "../forms/NumericField";

export default function AmbientSection() {
  const draft = useConfigStore((s) => s.draft);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  if (draft === null) return null;

  return (
    <Accordion id="ambient" index="13" label="Ambient">
      <div className="grid grid-cols-3 gap-3">
        <NumericField
          index="01"
          label="P Ambient"
          unit="kPa"
          value={draft.p_ambient}
          onChange={(v) => setField("p_ambient", v)}
          error={fieldErrors["p_ambient"]}
          displayScale={0.001}
          step={0.5}
        />
        <NumericField
          index="02"
          label="T Ambient"
          unit="K"
          value={draft.T_ambient}
          onChange={(v) => setField("T_ambient", v)}
          error={fieldErrors["T_ambient"]}
          step={1}
        />
        <NumericField
          index="03"
          label="Drivetrain Efficiency"
          unit="—"
          value={draft.drivetrain_efficiency}
          onChange={(v) => setField("drivetrain_efficiency", v)}
          error={fieldErrors["drivetrain_efficiency"]}
          step={0.01}
        />
      </div>
    </Accordion>
  );
}
