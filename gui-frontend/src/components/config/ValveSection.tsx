import { useConfigStore, type ValveKey } from "../../state/configStore";
import { Accordion } from "../forms/Accordion";
import { NumericField } from "../forms/NumericField";
import { CdTableEditor } from "../forms/CdTableEditor";

interface ValveSectionProps {
  valve: ValveKey;
  index: string;          // accordion index, e.g. "03"
  label: string;          // "Intake Valve" or "Exhaust Valve"
}

export default function ValveSection({ valve, index, label }: ValveSectionProps) {
  const draft = useConfigStore((s) => s.draft);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  if (draft === null) return null;
  const v = draft[valve];

  return (
    <Accordion id={valve} index={index} label={label}>
      <div className="grid grid-cols-3 gap-3">
        <NumericField
          index="01"
          label="Diameter"
          unit="mm"
          value={v.diameter}
          onChange={(n) => setField(`${valve}.diameter`, n)}
          error={fieldErrors[`${valve}.diameter`]}
          displayScale={1000}
          step={0.1}
        />
        <NumericField
          index="02"
          label="Max Lift"
          unit="mm"
          value={v.max_lift}
          onChange={(n) => setField(`${valve}.max_lift`, n)}
          error={fieldErrors[`${valve}.max_lift`]}
          displayScale={1000}
          step={0.1}
        />
        <NumericField
          index="03"
          label="Seat Angle"
          unit="deg"
          value={v.seat_angle}
          onChange={(n) => setField(`${valve}.seat_angle`, n)}
          error={fieldErrors[`${valve}.seat_angle`]}
          step={1}
        />
        <NumericField
          index="04"
          label="Open Angle"
          unit="deg"
          value={v.open_angle}
          onChange={(n) => setField(`${valve}.open_angle`, n)}
          error={fieldErrors[`${valve}.open_angle`]}
          step={1}
        />
        <NumericField
          index="05"
          label="Close Angle"
          unit="deg"
          value={v.close_angle}
          onChange={(n) => setField(`${valve}.close_angle`, n)}
          error={fieldErrors[`${valve}.close_angle`]}
          step={1}
        />
      </div>
      <CdTableEditor valve={valve} />
    </Accordion>
  );
}
