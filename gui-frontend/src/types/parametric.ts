/**
 * TypeScript mirrors of the backend parametric schema. Must stay in
 * sync with engine_simulator/gui/parametric/parameters.py and
 * study_manager.py.
 */

export interface Param {
  path: string;
  label: string;
  unit: string;
  default_range: [number, number, number];
  display_scale: number;
  min_allowed: number | null;
  max_allowed: number | null;
  category: string;
}

export interface ParametricStudyDef {
  study_id: string;
  name: string;
  config_name: string;
  parameter_path: string;
  parameter_values: number[];
  sweep_rpm_start: number;
  sweep_rpm_end: number;
  sweep_rpm_step: number;
  sweep_n_cycles: number;
  n_workers: number;
  created_at: string;
}

export type RunStatus = "queued" | "running" | "done" | "error";

export interface PerfDict {
  rpm: number;
  brake_power_hp?: number;
  brake_torque_Nm?: number;
  indicated_power_hp?: number;
  wheel_power_hp?: number;
  volumetric_efficiency_atm?: number;
  volumetric_efficiency_plenum?: number;
  plenum_pressure_bar?: number;
  imep_bar?: number;
  bmep_bar?: number;
  [key: string]: number | boolean | undefined;
}

export interface ParametricRun {
  parameter_value: number;
  status: RunStatus;
  sweep_results: PerfDict[];
  per_rpm_delta: Record<string, number>;
  elapsed_seconds: number;
  error: string | null;
}

export type StudyStatus = "running" | "complete" | "error" | "stopped";

export interface LiveParametricStudy {
  definition: ParametricStudyDef;
  status: StudyStatus;
  started_at: string;
  completed_at: string | null;
  error: string | null;
  runs: ParametricRun[];
}

export interface ParametricStudySummary {
  study_id: string;
  name: string;
  parameter_path: string;
  n_values: number;
  created_at: string;
  status: StudyStatus;
  run_count: number;
}

export type ObjectiveKey =
  | "peak_power"
  | "peak_torque"
  | "torque_area"
  | "power_at_rpm"
  | "torque_at_rpm";

export interface RunMetrics {
  peak_power_hp: number | null;
  peak_power_rpm: number | null;
  peak_torque_Nm: number | null;
  peak_torque_rpm: number | null;
  torque_area: number | null;
  power_at_rpm: number | null;
  torque_at_rpm: number | null;
  ve_peak: number | null;
  ve_avg: number | null;
}

export interface ComparisonRow {
  index: number;
  parameter_value: number;
  metrics: RunMetrics;
  status: RunStatus;
  rank: number | null;
  isBest: boolean;
  error: string | null;
}

// ---- WebSocket events ----

interface ParametricBase {
  channel: "parametric";
  study_id: string;
}

export type ParametricServerMessage =
  | (ParametricBase & {
      type: "parametric_snapshot";
      study: LiveParametricStudy | null;
    })
  | (ParametricBase & {
      type: "parametric_study_start";
      definition: ParametricStudyDef;
    })
  | (ParametricBase & {
      type: "parametric_value_start";
      parameter_value: number;
      value_index: number;
    })
  | (ParametricBase & {
      type: "parametric_rpm_start";
      parameter_value: number;
      rpm: number;
      rpm_index: number;
      n_cycles_target: number;
    })
  | (ParametricBase & {
      type: "parametric_rpm_cycle";
      parameter_value: number;
      rpm: number;
      cycle: number;
      delta: number | null;
      step_count: number;
      elapsed: number;
    })
  | (ParametricBase & {
      type: "parametric_rpm_done";
      parameter_value: number;
      rpm: number;
      perf: PerfDict;
      elapsed: number;
      converged: boolean;
    })
  | (ParametricBase & {
      type: "parametric_value_done";
      parameter_value: number;
      value_index: number;
      run: ParametricRun;
    })
  | (ParametricBase & {
      type: "parametric_value_error";
      parameter_value: number;
      value_index: number;
      error_msg: string;
    })
  | (ParametricBase & { type: "parametric_study_complete" })
  | (ParametricBase & { type: "parametric_study_stopped" })
  | (ParametricBase & { type: "parametric_study_error"; error_msg: string });
