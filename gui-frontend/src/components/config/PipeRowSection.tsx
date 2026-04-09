import { Accordion } from "../forms/Accordion";
import { PipeRow } from "../forms/PipeRow";

interface PipeRowSectionProps {
  index: string;
  label: string;
}

/**
 * Single-pipe section, currently used only for exhaust_collector.
 */
export default function PipeRowSection({ index, label }: PipeRowSectionProps) {
  return (
    <Accordion id="exhaust_collector" index={index} label={label}>
      <PipeRow singlePath="exhaust_collector" index="01" />
    </Accordion>
  );
}
