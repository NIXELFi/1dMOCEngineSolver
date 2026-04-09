// TypeScript types matching the WebSocket message schema in
// engine_simulator/gui/sweep_manager.py and gui/snapshot.py.
// Keep these in sync with the Python side.

export interface RpmStartEvent {
  type: "rpm_start";
  rpm: number;
  rpm_index: number;
  n_cycles_target: number;
  ts: number;
}

export interface CycleDoneEvent {
  type: "cycle_done";
  rpm: number;
  cycle: number;
  delta: number;
  p_ivc: number[];
  step_count: number;
  elapsed: number;
  ts: number;
}

export interface ConvergedEvent {
  type: "converged";
  rpm: number;
  cycle: number;
  ts: number;
}

export interface RpmDoneEvent {
  type: "rpm_done";
  rpm: number;
  perf: PerfDict;
  elapsed: number;
  step_count: number;
  converged: boolean;
  ts: number;
  results_available: boolean;
}

export interface RpmErrorEvent {
  type: "rpm_error";
  rpm: number;
  error_type: string;
  error_msg: string;
  traceback: string;
  ts: number;
}

export interface SweepCompleteEvent {
  type: "sweep_complete";
  sweep_id: string;
  filename?: string;
  duration_seconds?: number;
  stopped?: boolean;
}

export interface SweepErrorEvent {
  type: "sweep_error";
  error_msg: string;
  traceback: string;
}

export interface PongMessage {
  type: "pong";
}

export interface SnapshotMessage {
  type: "snapshot";
  sweep: SweepSnapshot | null;
  available_sweeps: SweepSummary[];
}

export interface SweepSnapshot {
  status: "running" | "complete" | "error" | "stopped" | "idle";
  sweep_id: string;
  config_summary: {
    rpm_start: number;
    rpm_end: number;
    rpm_step: number;
    n_cycles: number;
    n_workers: number;
    config_name: string;
  };
  rpm_points: number[];
  started_at: string;
  elapsed_seconds: number;
  rpms: Record<string, RpmState>;
  results_by_rpm_summary: Record<string, { available: boolean }>;
}

export interface RpmState {
  status: "queued" | "running" | "done" | "error";
  rpm_index: number;
  current_cycle?: number;
  // delta can be null when the convergence checker reports inf (first cycle).
  // The backend coerces non-finite floats to null before serializing.
  delta?: number | null;
  delta_history?: (number | null)[];
  p_ivc_history?: number[][];
  step_count?: number;
  elapsed?: number;
  perf?: PerfDict;
  converged?: boolean;
  converged_at_cycle?: number;
  error_type?: string;
  error_msg?: string;
  traceback?: string;
  // Frontend-only field: wall-clock millisecond timestamp captured when the
  // rpm transitioned to "running". Used by WorkerTile to display a live
  // ticking elapsed counter between cycle_done events.
  client_started_at_ms?: number;
}

export interface PerfDict {
  rpm: number;
  indicated_power_hp: number;
  indicated_power_kW?: number;
  indicated_torque_Nm?: number;
  brake_power_hp: number;
  brake_power_kW?: number;
  brake_torque_Nm: number;
  wheel_power_hp?: number;
  wheel_power_kW?: number;
  wheel_torque_Nm?: number;
  drivetrain_efficiency?: number;
  imep_bar?: number;
  bmep_bar?: number;
  fmep_bar?: number;
  volumetric_efficiency_atm: number;
  volumetric_efficiency_plenum?: number;
  volumetric_efficiency?: number;
  intake_mass_per_cycle_g?: number;
  restrictor_choked?: boolean;
  restrictor_mdot?: number;
  plenum_pressure_bar?: number;
}

export interface SweepSummary {
  id: string;
  filename: string;
  started_at: string;
  duration_seconds: number;
  rpm_range: [number, number];
  n_rpm_points: number;
}

export type ServerMessage =
  | SnapshotMessage
  | RpmStartEvent
  | CycleDoneEvent
  | ConvergedEvent
  | RpmDoneEvent
  | RpmErrorEvent
  | SweepCompleteEvent
  | SweepErrorEvent
  | PongMessage;
