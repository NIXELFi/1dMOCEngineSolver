import { useConfigStore } from "../../state/configStore";
import { Accordion } from "../forms/Accordion";
import { NumericField } from "../forms/NumericField";
import { TextField } from "../forms/TextField";

export default function IdentitySection() {
  const draft = useConfigStore((s) => s.draft);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  if (draft === null) return null;

  return (
    <Accordion id="identity" index="01" label="Identity">
      <div className="grid grid-cols-2 gap-3">
        <TextField
          index="01"
          label="Name"
          value={draft.name}
          onChange={(v) => setField("name", v)}
          error={fieldErrors["name"]}
        />
        <TextField
          index="02"
          label="Firing Order"
          unit="cyl"
          value={draft.firing_order.join(",")}
          onChange={(v) => {
            const parts = v
              .split(",")
              .map((s) => Number(s.trim()))
              .filter((n) => Number.isFinite(n));
            setField("firing_order", parts);
          }}
          error={fieldErrors["firing_order"]}
          placeholder="1,2,4,3"
        />
        <NumericField
          index="03"
          label="N Cylinders"
          unit="cyl"
          value={draft.n_cylinders}
          onChange={(v) => setField("n_cylinders", v)}
          error={fieldErrors["n_cylinders"]}
          step={1}
          min={1}
        />
        <NumericField
          index="04"
          label="Firing Interval"
          unit="deg"
          value={draft.firing_interval}
          onChange={(v) => setField("firing_interval", v)}
          error={fieldErrors["firing_interval"]}
          step={1}
        />
      </div>
    </Accordion>
  );
}
