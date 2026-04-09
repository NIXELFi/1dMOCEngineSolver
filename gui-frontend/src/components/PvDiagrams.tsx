import type { SimulationResultsData } from "./RpmDetail";

interface PvDiagramsProps {
  /**
   * Accepted for API symmetry with CylinderTraces and to make the v1 → v1.x
   * transition a type-only change once engine geometry is exposed via the
   * backend. Intentionally unused right now.
   */
  results: SimulationResultsData;
}

/* ========================================================================= */
/* PvDiagrams — placeholder for the P-V indicator diagram tab                */
/*                                                                           */
/* For v1 we cannot draw true P-V curves: the backend's per-RPM results     */
/* payload includes pressure / temperature / density per crank angle but    */
/* not cylinder volume, which would require access to the `EngineConfig`    */
/* geometry (bore, stroke, con-rod length, compression ratio). That data   */
/* lives in `EngineConfig.cylinder` on the Python side and is not exposed  */
/* by `GET /api/sweeps/current/results/{rpm}`.                             */
/*                                                                           */
/* A future phase will add a `/api/configs/{name}` (or similar) endpoint   */
/* to return the EngineConfig JSON; at that point this component can      */
/* compute V(theta) from the slider-crank kinematics and render proper     */
/* P-V indicator diagrams (one per cylinder, with a log-log toggle per the */
/* design spec).                                                            */
/*                                                                           */
/* Until then we render an honest "deferred" placeholder that matches the  */
/* existing instrument-panel empty-state grammar used elsewhere in the    */
/* detail panel.                                                           */
/* ========================================================================= */

export default function PvDiagrams(_props: PvDiagramsProps) {
  // Suppress unused-prop warning without stripping the prop from the type.
  void _props;

  return (
    <div className="py-10 flex items-center justify-center">
      <div className="flex flex-col items-center gap-3 max-w-[460px]">
        {/* Tiny muted dot + hairline divider — same grammar as the other
            empty states inside RpmDetail and the SweepCurves EmptyState. */}
        <span
          className="inline-block w-1.5 h-1.5 rounded-full bg-text-muted"
          aria-hidden
        />
        <div className="w-16 h-px bg-border-default" aria-hidden />

        {/* Primary line — matches the uppercase-tracked empty-state tone. */}
        <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-text-muted leading-none text-center">
          P-V Diagrams Require Cylinder Geometry
        </p>

        {/* Secondary explanation — kept in a slightly smaller, non-upper-
            case tone so it reads as a subordinate clarification. */}
        <p className="text-[10px] font-mono text-text-muted/70 leading-snug text-center">
          Awaiting engine geometry via the configs endpoint.
          <br />
          Scheduled for Phase&nbsp;J6.
        </p>
      </div>
    </div>
  );
}
