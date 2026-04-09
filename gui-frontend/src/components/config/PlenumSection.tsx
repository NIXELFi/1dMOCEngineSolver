import { useConfigStore } from "../../state/configStore";
import { Accordion } from "../forms/Accordion";
import { NumericField } from "../forms/NumericField";

export default function PlenumSection() {
  const draft = useConfigStore((s) => s.draft);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  if (draft === null) return null;
  const p = draft.plenum;

  return (
    <Accordion id="plenum" index="11" label="Plenum">
      <div className="grid grid-cols-3 gap-3">
        <NumericField
          index="01"
          label="Volume"
          unit="L"
          value={p.volume}
          onChange={(v) => setField("plenum.volume", v)}
          error={fieldErrors["plenum.volume"]}
          displayScale={1000}
          step={0.05}
        />
        <NumericField
          index="02"
          label="Initial Pressure"
          unit="kPa"
          value={p.initial_pressure}
          onChange={(v) => setField("plenum.initial_pressure", v)}
          error={fieldErrors["plenum.initial_pressure"]}
          displayScale={0.001}
          step={0.5}
        />
        <NumericField
          index="03"
          label="Initial Temperature"
          unit="K"
          value={p.initial_temperature}
          onChange={(v) => setField("plenum.initial_temperature", v)}
          error={fieldErrors["plenum.initial_temperature"]}
          step={1}
        />
      </div>
    </Accordion>
  );
}
