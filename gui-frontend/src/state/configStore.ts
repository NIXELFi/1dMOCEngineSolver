import { create } from "zustand";
import type { ConfigSummary } from "../api/client";

/* ========================================================================== */
/* Payload types — must match engine_simulator/gui/config_schema.py            */
/* ========================================================================== */

export interface CylinderPayload {
  bore: number;
  stroke: number;
  con_rod_length: number;
  compression_ratio: number;
  n_intake_valves: number;
  n_exhaust_valves: number;
}

export interface ValvePayload {
  diameter: number;
  max_lift: number;
  open_angle: number;
  close_angle: number;
  seat_angle: number;
  cd_table: [number, number][];
}

export interface PipePayload {
  name: string;
  length: number;
  diameter: number;
  diameter_out: number | null;
  n_points: number;
  wall_temperature: number;
  roughness: number;
}

export interface CombustionPayload {
  wiebe_a: number;
  wiebe_m: number;
  combustion_duration: number;
  spark_advance: number;
  ignition_delay: number;
  combustion_efficiency: number;
  q_lhv: number;
  afr_stoich: number;
  afr_target: number;
}

export interface RestrictorPayload {
  throat_diameter: number;
  discharge_coefficient: number;
  converging_half_angle: number;
  diverging_half_angle: number;
}

export interface PlenumPayload {
  volume: number;
  initial_pressure: number;
  initial_temperature: number;
}

export interface SimulationPayload {
  rpm_start: number;
  rpm_end: number;
  rpm_step: number;
  n_cycles: number;
  cfl_number: number;
  convergence_tolerance: number;
  crank_step_max: number;
  artificial_viscosity: number;
}

export interface EngineConfigPayload {
  name: string;
  n_cylinders: number;
  firing_order: number[];
  firing_interval: number;
  cylinder: CylinderPayload;
  intake_valve: ValvePayload;
  exhaust_valve: ValvePayload;
  intake_pipes: PipePayload[];
  exhaust_primaries: PipePayload[];
  exhaust_secondaries: PipePayload[];
  exhaust_collector: PipePayload;
  combustion: CombustionPayload;
  restrictor: RestrictorPayload;
  plenum: PlenumPayload;
  simulation: SimulationPayload;
  p_ambient: number;
  T_ambient: number;
  drivetrain_efficiency: number;
}

export type PipeArrayKey =
  | "intake_pipes"
  | "exhaust_primaries"
  | "exhaust_secondaries";

export type ValveKey = "intake_valve" | "exhaust_valve";

/* ========================================================================== */
/* Store                                                                      */
/* ========================================================================== */

export type ActiveTab = "simulation" | "config" | "dyno";

export interface ConfigStore {
  // Catalog
  available: ConfigSummary[];

  // Active document
  activeName: string | null;
  saved: EngineConfigPayload | null;
  draft: EngineConfigPayload | null;

  // UI
  activeTab: ActiveTab;
  expandedSections: Record<string, boolean>;

  // Status
  loading: boolean;
  saving: boolean;
  loadError: string | null;
  saveError: string | null;
  saveFlash: number | null;
  fieldErrors: Record<string, string>;

  // Actions
  setActiveTab: (tab: ActiveTab) => void;
  setAvailable: (list: ConfigSummary[]) => void;
  setActive: (
    name: string,
    payload: EngineConfigPayload,
  ) => void;
  setLoading: (loading: boolean) => void;
  setLoadError: (error: string | null) => void;
  setSaving: (saving: boolean) => void;
  setSaveError: (error: string | null) => void;
  setFieldErrors: (errors: Record<string, string>) => void;
  flashSaved: () => void;
  setField: (path: string, value: unknown) => void;
  addPipe: (section: PipeArrayKey) => void;
  removePipe: (section: PipeArrayKey, index: number) => void;
  addCdRow: (valve: ValveKey) => void;
  removeCdRow: (valve: ValveKey, index: number) => void;
  revert: () => void;
  toggleSection: (id: string) => void;
}

/* ----- helpers ----- */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function setByPath(obj: any, path: string, value: unknown): any {
  const segments = path.split(".");
  if (segments.length === 0) return value;
  const next = Array.isArray(obj) ? [...obj] : { ...obj };
  let cur = next;
  for (let i = 0; i < segments.length - 1; i++) {
    const seg = segments[i];
    const child = cur[seg];
    cur[seg] = Array.isArray(child) ? [...child] : { ...child };
    cur = cur[seg];
  }
  cur[segments[segments.length - 1]] = value;
  return next;
}

const DEFAULT_PIPE = (name: string): PipePayload => ({
  name,
  length: 0.25,
  diameter: 0.038,
  diameter_out: null,
  n_points: 30,
  wall_temperature: 325.0,
  roughness: 3e-5,
});

const DEFAULT_CD_ROW: [number, number] = [0.1, 0.4];

/* ----- store ----- */

export const useConfigStore = create<ConfigStore>((set) => ({
  available: [],
  activeName: null,
  saved: null,
  draft: null,
  activeTab: "simulation",
  expandedSections: {},
  loading: false,
  saving: false,
  loadError: null,
  saveError: null,
  saveFlash: null,
  fieldErrors: {},

  setActiveTab: (tab) => set({ activeTab: tab }),
  setAvailable: (list) => set({ available: list }),
  setActive: (name, payload) =>
    set({
      activeName: name,
      saved: payload,
      draft: payload,
      fieldErrors: {},
      saveError: null,
      loadError: null,
    }),
  setLoading: (loading) => set({ loading }),
  setLoadError: (error) => set({ loadError: error }),
  setSaving: (saving) => set({ saving }),
  setSaveError: (error) => set({ saveError: error }),
  setFieldErrors: (errors) => set({ fieldErrors: errors }),
  flashSaved: () => set({ saveFlash: Date.now() }),

  setField: (path, value) =>
    set((s) => {
      if (s.draft === null) return s;
      return { draft: setByPath(s.draft, path, value) };
    }),

  addPipe: (section) =>
    set((s) => {
      if (s.draft === null) return s;
      const list = s.draft[section];
      const newName = `${section}_${list.length + 1}`;
      return {
        draft: setByPath(s.draft, section, [...list, DEFAULT_PIPE(newName)]),
      };
    }),

  removePipe: (section, index) =>
    set((s) => {
      if (s.draft === null) return s;
      const list = s.draft[section].filter((_, i) => i !== index);
      return { draft: setByPath(s.draft, section, list) };
    }),

  addCdRow: (valve) =>
    set((s) => {
      if (s.draft === null) return s;
      const rows: [number, number][] = [
        ...s.draft[valve].cd_table,
        DEFAULT_CD_ROW,
      ];
      return { draft: setByPath(s.draft, `${valve}.cd_table`, rows) };
    }),

  removeCdRow: (valve, index) =>
    set((s) => {
      if (s.draft === null) return s;
      const rows = s.draft[valve].cd_table.filter((_, i) => i !== index);
      return { draft: setByPath(s.draft, `${valve}.cd_table`, rows) };
    }),

  revert: () =>
    set((s) => ({
      draft: s.saved,
      fieldErrors: {},
      saveError: null,
    })),

  toggleSection: (id) =>
    set((s) => ({
      expandedSections: {
        ...s.expandedSections,
        [id]: !(s.expandedSections[id] ?? true),
      },
    })),
}));

/* ========================================================================== */
/* Selectors                                                                  */
/* ========================================================================== */

export const selectIsDirty = (s: ConfigStore): boolean => {
  if (s.draft === null || s.saved === null) return false;
  return JSON.stringify(s.draft) !== JSON.stringify(s.saved);
};

export const selectIsSectionOpen = (id: string) => (s: ConfigStore): boolean => {
  return s.expandedSections[id] ?? true;
};
