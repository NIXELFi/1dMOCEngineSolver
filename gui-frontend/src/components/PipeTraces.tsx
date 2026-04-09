import { useMemo } from "react";
import LineChart from "./charts/LineChart";
import type { SimulationResultsData } from "./RpmDetail";

/* ========================================================================= */
/* Types                                                                     */
/* ========================================================================= */

interface PipeTracesProps {
  results: SimulationResultsData;
}

/** A chart row for a single pipe trace: theta (deg), pressure (bar). */
interface PipeRow {
  theta: number;
  pressure: number;
  [extraKey: string]: number | boolean | undefined;
}

/** Per-pipe derived display data. */
interface PipeDerived {
  probeKey: string;   // "intake_runner_1_mid"
  ordinal: string;    // "I1", "E1", "S1", "CL"
  title: string;      // "INTAKE RUNNER 1"
  rows: PipeRow[];
}

/* ========================================================================= */
/* Pipe grouping — the 11 probes the backend emits, split by section         */
/* ========================================================================= */

/**
 * Pipe sections. Each section renders as its own header strip + grid of
 * pipe panels. Ordinals mirror the instrument-panel grammar used by
 * CylinderTraces (`C1..C4`) but scoped to the pipe type:
 *
 *   I1..I4 = intake runners
 *   E1..E4 = exhaust primaries
 *   S1..S2 = exhaust secondaries
 *   CL     = collector
 *
 * The probe-key suffix is always `_mid` (the midpoint probe), per
 * `persistence.py:_serialize_results` on the Python side.
 */
interface PipeSection {
  label: string;          // section header text, e.g. "INTAKE RUNNERS"
  ordinalPrefix: string;  // "I", "E", "S", or "" for single collector
  gridClass: string;      // tailwind grid classes for that row
  pipes: Array<{
    probeKey: string;
    ordinal: string;
    title: string;
  }>;
}

const PIPE_SECTIONS: PipeSection[] = [
  {
    label: "Intake Runners",
    ordinalPrefix: "I",
    gridClass: "grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-2",
    pipes: [
      { probeKey: "intake_runner_1_mid", ordinal: "I1", title: "Intake Runner 1" },
      { probeKey: "intake_runner_2_mid", ordinal: "I2", title: "Intake Runner 2" },
      { probeKey: "intake_runner_3_mid", ordinal: "I3", title: "Intake Runner 3" },
      { probeKey: "intake_runner_4_mid", ordinal: "I4", title: "Intake Runner 4" },
    ],
  },
  {
    label: "Exhaust Primaries",
    ordinalPrefix: "E",
    gridClass: "grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-2",
    pipes: [
      { probeKey: "exhaust_primary_1_mid", ordinal: "E1", title: "Exhaust Primary 1" },
      { probeKey: "exhaust_primary_2_mid", ordinal: "E2", title: "Exhaust Primary 2" },
      { probeKey: "exhaust_primary_3_mid", ordinal: "E3", title: "Exhaust Primary 3" },
      { probeKey: "exhaust_primary_4_mid", ordinal: "E4", title: "Exhaust Primary 4" },
    ],
  },
  {
    label: "Exhaust Secondaries",
    ordinalPrefix: "S",
    gridClass: "grid grid-cols-1 sm:grid-cols-2 gap-2",
    pipes: [
      { probeKey: "exhaust_secondary_1_mid", ordinal: "S1", title: "Exhaust Secondary 1" },
      { probeKey: "exhaust_secondary_2_mid", ordinal: "S2", title: "Exhaust Secondary 2" },
    ],
  },
  {
    label: "Collector",
    ordinalPrefix: "",
    gridClass: "grid grid-cols-1 gap-2",
    pipes: [
      { probeKey: "exhaust_collector_mid", ordinal: "CL", title: "Exhaust Collector" },
    ],
  },
];

/* ========================================================================= */
/* Accent palette — one magenta per family, keeps the eye oriented           */
/*                                                                           */
/* We reuse `chart-restrictor` magenta from SweepCurves as the pipe palette  */
/* root (distinct from the 4 cylinder reds/blues/greens). Intake pipes get  */
/* the cool blue variant; exhaust the warmer magenta; the collector picks   */
/* up the amber used for the convergence band.                              */
/* ========================================================================= */

const SECTION_COLORS: Record<string, string> = {
  Intake: "#6BC5D8",               // cool desaturated cyan
  "Exhaust Primaries": "#C586E8",  // chart-restrictor magenta
  "Exhaust Secondaries": "#B97AD6",// slightly darker magenta — mid-tier
  Collector: "#E8A34A",            // warm amber — the "last stop"
};

function colorFor(label: string): string {
  if (label.toLowerCase().startsWith("intake")) return SECTION_COLORS["Intake"];
  if (label === "Exhaust Primaries") return SECTION_COLORS["Exhaust Primaries"];
  if (label === "Exhaust Secondaries") return SECTION_COLORS["Exhaust Secondaries"];
  return SECTION_COLORS["Collector"];
}

/* ========================================================================= */
/* PipeTraces — the "Pipes" tab body inside RpmDetail                         */
/* ========================================================================= */

/**
 * PipeTraces — renders the 11 midpoint pipe pressure traces grouped into
 * four sections (intake runners, exhaust primaries, exhaust secondaries,
 * collector) per §4 of the design spec.
 *
 * Each panel is a small LineChart of pressure (Pa → bar) vs crank angle,
 * windowed to the last 720° of the recorded history (same approach as
 * CylinderTraces) so the chart never draws cycle-wrap lines.
 *
 * v1 renders pressure only. Velocity twin-axis and the crank-angle hover
 * sync described in the spec are deferred to a future phase — see the
 * report-back note.
 */
export default function PipeTraces({ results }: PipeTracesProps) {
  /* ---- Derive every pipe's filtered/shifted rows once -------------------- */
  const derivedBySection = useMemo<
    Array<{ section: PipeSection; pipes: PipeDerived[]; color: string }>
  >(() => {
    return PIPE_SECTIONS.map((section) => {
      const color = colorFor(section.label);
      const pipes: PipeDerived[] = section.pipes.map((pipe) => {
        const probe = results.pipe_probes[pipe.probeKey];
        if (!probe || !probe.theta || probe.theta.length === 0) {
          return {
            probeKey: pipe.probeKey,
            ordinal: pipe.ordinal,
            title: pipe.title,
            rows: [],
          };
        }

        // Find max theta so we can slice to the last cycle.
        let maxTheta = -Infinity;
        for (const t of probe.theta) {
          if (Number.isFinite(t) && t > maxTheta) maxTheta = t;
        }
        if (!Number.isFinite(maxTheta)) {
          return {
            probeKey: pipe.probeKey,
            ordinal: pipe.ordinal,
            title: pipe.title,
            rows: [],
          };
        }
        const cutoff = maxTheta - 720;

        const rows: PipeRow[] = [];
        const n = Math.min(probe.theta.length, probe.pressure.length);
        for (let k = 0; k < n; k++) {
          const t = probe.theta[k];
          if (!Number.isFinite(t) || t < cutoff) continue;
          const p = probe.pressure[k];
          if (!Number.isFinite(p)) continue;
          rows.push({
            theta: t - cutoff,
            pressure: p / 1e5,
          });
        }
        return {
          probeKey: pipe.probeKey,
          ordinal: pipe.ordinal,
          title: pipe.title,
          rows,
        };
      });
      return { section, pipes, color };
    });
  }, [results]);

  /* ---- Render ----------------------------------------------------------- */
  return (
    <div className="flex flex-col gap-3">
      {derivedBySection.map(({ section, pipes, color }) => (
        <SectionBlock
          key={section.label}
          label={section.label}
          gridClass={section.gridClass}
          count={pipes.length}
        >
          {pipes.map((pipe) => (
            <PipePanel
              key={pipe.probeKey}
              ordinal={pipe.ordinal}
              title={pipe.title.toUpperCase()}
              nPoints={pipe.rows.length}
              accent={color}
            >
              {pipe.rows.length === 0 ? (
                <NoData />
              ) : (
                <LineChart
                  data={pipe.rows}
                  xKey="theta"
                  series={[
                    { key: "pressure", label: "P", color },
                  ]}
                  yLabel="P · BAR"
                  height={150}
                  showDots={false}
                />
              )}
            </PipePanel>
          ))}
        </SectionBlock>
      ))}
    </div>
  );
}

/* ========================================================================= */
/* SectionBlock — the "INTAKE RUNNERS" group chrome                          */
/*                                                                           */
/* A thin hairline-topped strip that acts as a section header. Mirrors the  */
/* tiny-label grammar used on the RpmDetail tab row, and pairs a bracketed  */
/* group ordinal ([G]) with the label and pipe count so the section reads  */
/* like a Bloomberg-terminal subheading rather than a generic card title.   */
/* ========================================================================= */

function SectionBlock({
  label,
  gridClass,
  count,
  children,
}: {
  label: string;
  gridClass: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-1.5" aria-label={label}>
      {/* Header strip */}
      <header className="flex items-center gap-2 pb-1 border-b border-border-default/70">
        <span className="text-[9px] font-mono text-text-muted leading-none tabular-nums">
          [G]
        </span>
        <h3 className="text-[10px] font-semibold uppercase tracking-[0.22em] text-text-secondary leading-none">
          {label}
        </h3>
        <div className="flex-1 h-px bg-border-default/50" aria-hidden />
        <span className="text-[9px] font-mono uppercase tracking-[0.14em] text-text-muted leading-none">
          n=
        </span>
        <span className="text-[9px] font-mono tabular-nums text-text-muted leading-none">
          {String(count).padStart(2, "0")}
        </span>
      </header>

      {/* Grid of pipe panels */}
      <div className={gridClass}>{children}</div>
    </section>
  );
}

/* ========================================================================= */
/* PipePanel — bordered chrome for a single pipe trace                       */
/*                                                                           */
/* Mirrors CylinderPanel but scoped to pipes — ordinal swatch + bracketed   */
/* ordinal + uppercase title + a sample-count readout in the right cluster. */
/* ========================================================================= */

function PipePanel({
  ordinal,
  title,
  nPoints,
  accent,
  children,
}: {
  ordinal: string;
  title: string;
  nPoints: number;
  accent: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className="flex flex-col bg-surface-raised border border-border-default rounded font-ui"
      aria-label={title}
    >
      <header className="flex items-stretch border-b border-border-default">
        <div className="flex-1 flex items-center gap-2 px-2.5 py-1.5 min-w-0">
          <span
            className="inline-block w-[3px] h-3"
            style={{ backgroundColor: accent }}
            aria-hidden
          />
          <span className="text-[9px] font-mono text-text-muted leading-none tabular-nums">
            [{ordinal}]
          </span>
          <h4 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-text-primary leading-none truncate">
            {title}
          </h4>
        </div>

        <div className="flex items-center gap-1 px-2.5 border-l border-border-default">
          <span className="text-[9px] font-mono uppercase tracking-[0.14em] text-text-muted leading-none">
            n
          </span>
          <span className="text-[9px] font-mono text-text-muted leading-none">
            =
          </span>
          <span className="text-[9px] font-mono tabular-nums text-text-secondary leading-none">
            {formatCount(nPoints)}
          </span>
        </div>
      </header>

      <div className="p-2.5">{children}</div>
    </section>
  );
}

/* ========================================================================= */
/* NoData — compact in-panel empty state                                     */
/* ========================================================================= */

function NoData() {
  return (
    <div className="h-[150px] flex flex-col items-center justify-center gap-2">
      <span
        className="inline-block w-1.5 h-1.5 rounded-full bg-text-muted"
        aria-hidden
      />
      <div className="w-10 h-px bg-border-default" aria-hidden />
      <span className="text-[9px] font-mono font-semibold uppercase tracking-[0.22em] text-text-muted leading-none">
        No Data
      </span>
    </div>
  );
}

/* ========================================================================= */
/* Helpers                                                                    */
/* ========================================================================= */

function formatCount(n: number): string {
  if (n < 100) return String(n).padStart(2, "0");
  if (n < 10000) return String(n);
  return `${Math.round(n / 1000)}k`;
}
