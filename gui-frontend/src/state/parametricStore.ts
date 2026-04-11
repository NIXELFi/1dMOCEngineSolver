import { create } from "zustand";
import type {
  LiveParametricStudy,
  ObjectiveKey,
  Param,
  ParametricRun,
  ParametricStudySummary,
  PerfDict,
} from "../types/parametric";

interface ParametricState {
  // Current live or loaded study
  current: LiveParametricStudy | null;

  // Past studies list (sidebar)
  studies: ParametricStudySummary[];
  studiesLoading: boolean;
  studiesError: string | null;

  // Sweepable parameters (loaded once at mount)
  availableParameters: Param[];
  parametersLoaded: boolean;

  // Results-view UI state
  selectedObjective: ObjectiveKey;
  objectiveRpm: number;
  objectiveRpmWindow: [number, number];
  selectedRunIndices: Set<number>;
  highlightedRunIndex: number | null;

  // Setter actions
  setCurrent: (study: LiveParametricStudy | null) => void;
  setStudies: (studies: ParametricStudySummary[]) => void;
  setStudiesLoading: (loading: boolean) => void;
  setStudiesError: (err: string | null) => void;
  setAvailableParameters: (params: Param[]) => void;
  setSelectedObjective: (obj: ObjectiveKey) => void;
  setObjectiveRpm: (rpm: number) => void;
  setObjectiveRpmWindow: (w: [number, number]) => void;
  toggleRunSelected: (index: number) => void;
  selectAllRuns: () => void;
  clearSelectedRuns: () => void;
  setHighlightedRun: (index: number | null) => void;
  clearCurrent: () => void;

  // Reducer-invoked mutations (internal to eventReducer)
  _applyStudyStart: (
    study_id: string,
    definition: LiveParametricStudy["definition"],
  ) => void;
  _applyValueStart: (value_index: number) => void;
  _applyRpmDone: (
    value_index: number,
    rpm: number,
    perf: PerfDict,
  ) => void;
  _applyValueDone: (value_index: number, run: ParametricRun) => void;
  _applyValueError: (
    value_index: number,
    error_msg: string,
  ) => void;
  _applyStudyComplete: () => void;
  _applyStudyStopped: () => void;
  _applyStudyError: (error_msg: string) => void;
}

export const useParametricStore = create<ParametricState>((set, get) => ({
  current: null,
  studies: [],
  studiesLoading: false,
  studiesError: null,
  availableParameters: [],
  parametersLoaded: false,

  selectedObjective: "peak_power",
  objectiveRpm: 9000,
  objectiveRpmWindow: [6000, 12000],
  selectedRunIndices: new Set<number>(),
  highlightedRunIndex: null,

  setCurrent: (study) => {
    const selected = new Set<number>();
    if (study) {
      study.runs.forEach((_, i) => selected.add(i));
    }
    set({ current: study, selectedRunIndices: selected });
  },
  setStudies: (studies) => set({ studies }),
  setStudiesLoading: (studiesLoading) => set({ studiesLoading }),
  setStudiesError: (studiesError) => set({ studiesError }),
  setAvailableParameters: (availableParameters) =>
    set({ availableParameters, parametersLoaded: true }),
  setSelectedObjective: (selectedObjective) => set({ selectedObjective }),
  setObjectiveRpm: (objectiveRpm) => set({ objectiveRpm }),
  setObjectiveRpmWindow: (objectiveRpmWindow) => set({ objectiveRpmWindow }),
  toggleRunSelected: (index) => {
    const next = new Set(get().selectedRunIndices);
    if (next.has(index)) {
      next.delete(index);
    } else {
      next.add(index);
    }
    set({ selectedRunIndices: next });
  },
  selectAllRuns: () => {
    const current = get().current;
    if (!current) return;
    const next = new Set<number>();
    current.runs.forEach((_, i) => next.add(i));
    set({ selectedRunIndices: next });
  },
  clearSelectedRuns: () => set({ selectedRunIndices: new Set() }),
  setHighlightedRun: (highlightedRunIndex) => set({ highlightedRunIndex }),
  clearCurrent: () =>
    set({
      current: null,
      selectedRunIndices: new Set(),
      highlightedRunIndex: null,
    }),

  _applyStudyStart: (_study_id, definition) => {
    set({
      current: {
        definition,
        status: "running",
        started_at: new Date().toISOString(),
        completed_at: null,
        error: null,
        runs: definition.parameter_values.map((v) => ({
          parameter_value: v,
          status: "queued" as const,
          sweep_results: [],
          per_rpm_delta: {},
          elapsed_seconds: 0,
          error: null,
        })),
      },
      selectedRunIndices: new Set(
        definition.parameter_values.map((_, i) => i),
      ),
    });
  },

  _applyValueStart: (value_index) => {
    const current = get().current;
    if (!current) return;
    const runs = current.runs.map((r, i) =>
      i === value_index ? { ...r, status: "running" as const } : r,
    );
    set({ current: { ...current, runs } });
  },

  _applyRpmDone: (value_index, rpm, perf) => {
    const current = get().current;
    if (!current) return;
    const runs = current.runs.map((r, i) => {
      if (i !== value_index) return r;
      const existingIdx = r.sweep_results.findIndex((p) => p.rpm === rpm);
      const nextResults =
        existingIdx >= 0
          ? r.sweep_results.map((p, j) => (j === existingIdx ? perf : p))
          : [...r.sweep_results, perf];
      // Keep sorted by RPM so charts render correctly
      nextResults.sort((a, b) => a.rpm - b.rpm);
      return { ...r, sweep_results: nextResults };
    });
    set({ current: { ...current, runs } });
  },

  _applyValueDone: (value_index, run) => {
    const current = get().current;
    if (!current) return;
    const runs = current.runs.map((r, i) => (i === value_index ? run : r));
    set({ current: { ...current, runs } });
  },

  _applyValueError: (value_index, error_msg) => {
    const current = get().current;
    if (!current) return;
    const runs = current.runs.map((r, i) =>
      i === value_index
        ? { ...r, status: "error" as const, error: error_msg }
        : r,
    );
    set({ current: { ...current, runs } });
  },

  _applyStudyComplete: () => {
    const current = get().current;
    if (!current) return;
    set({
      current: {
        ...current,
        status: "complete",
        completed_at: new Date().toISOString(),
      },
    });
  },

  _applyStudyStopped: () => {
    const current = get().current;
    if (!current) return;
    set({
      current: {
        ...current,
        status: "stopped",
        completed_at: new Date().toISOString(),
      },
    });
  },

  _applyStudyError: (error_msg) => {
    const current = get().current;
    if (!current) return;
    set({
      current: {
        ...current,
        status: "error",
        error: error_msg,
        completed_at: new Date().toISOString(),
      },
    });
  },
}));
