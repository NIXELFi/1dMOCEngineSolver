import { useConfigStore } from "../../state/configStore";
import { Accordion } from "../forms/Accordion";
import { NumericField } from "../forms/NumericField";

export default function CylinderSection() {
  const draft = useConfigStore((s) => s.draft);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  if (draft === null) return null;
  const c = draft.cylinder;

  return (
    <Accordion id="cylinder" index="02" label="Cylinder">
      <div className="grid grid-cols-2 gap-3">
        <NumericField
          index="01"
          label="Bore"
          unit="mm"
          value={c.bore}
          onChange={(v) => setField("cylinder.bore", v)}
          error={fieldErrors["cylinder.bore"]}
          displayScale={1000}
          step={0.1}
          min={0}
        />
        <NumericField
          index="02"
          label="Stroke"
          unit="mm"
          value={c.stroke}
          onChange={(v) => setField("cylinder.stroke", v)}
          error={fieldErrors["cylinder.stroke"]}
          displayScale={1000}
          step={0.1}
          min={0}
        />
        <NumericField
          index="03"
          label="Con Rod Length"
          unit="mm"
          value={c.con_rod_length}
          onChange={(v) => setField("cylinder.con_rod_length", v)}
          error={fieldErrors["cylinder.con_rod_length"]}
          displayScale={1000}
          step={0.1}
          min={0}
        />
        <NumericField
          index="04"
          label="Compression Ratio"
          unit="—"
          value={c.compression_ratio}
          onChange={(v) => setField("cylinder.compression_ratio", v)}
          error={fieldErrors["cylinder.compression_ratio"]}
          step={0.1}
          min={1}
        />
        <NumericField
          index="05"
          label="N Intake Valves"
          unit="n"
          value={c.n_intake_valves}
          onChange={(v) => setField("cylinder.n_intake_valves", v)}
          error={fieldErrors["cylinder.n_intake_valves"]}
          step={1}
          min={1}
        />
        <NumericField
          index="06"
          label="N Exhaust Valves"
          unit="n"
          value={c.n_exhaust_valves}
          onChange={(v) => setField("cylinder.n_exhaust_valves", v)}
          error={fieldErrors["cylinder.n_exhaust_valves"]}
          step={1}
          min={1}
        />
      </div>
    </Accordion>
  );
}
