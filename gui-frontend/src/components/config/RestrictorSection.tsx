import { useConfigStore } from "../../state/configStore";
import { Accordion } from "../forms/Accordion";
import { NumericField } from "../forms/NumericField";

export default function RestrictorSection() {
  const draft = useConfigStore((s) => s.draft);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  if (draft === null) return null;
  const r = draft.restrictor;

  return (
    <Accordion id="restrictor" index="10" label="Restrictor">
      <div className="grid grid-cols-2 gap-3">
        <NumericField
          index="01"
          label="Throat Diameter"
          unit="mm"
          value={r.throat_diameter}
          onChange={(v) => setField("restrictor.throat_diameter", v)}
          error={fieldErrors["restrictor.throat_diameter"]}
          displayScale={1000}
          step={0.1}
        />
        <NumericField
          index="02"
          label="Discharge Coefficient"
          unit="—"
          value={r.discharge_coefficient}
          onChange={(v) => setField("restrictor.discharge_coefficient", v)}
          error={fieldErrors["restrictor.discharge_coefficient"]}
          step={0.001}
        />
        <NumericField
          index="03"
          label="Converging Half Angle"
          unit="deg"
          value={r.converging_half_angle}
          onChange={(v) => setField("restrictor.converging_half_angle", v)}
          error={fieldErrors["restrictor.converging_half_angle"]}
          step={0.5}
        />
        <NumericField
          index="04"
          label="Diverging Half Angle"
          unit="deg"
          value={r.diverging_half_angle}
          onChange={(v) => setField("restrictor.diverging_half_angle", v)}
          error={fieldErrors["restrictor.diverging_half_angle"]}
          step={0.5}
        />
      </div>
    </Accordion>
  );
}
