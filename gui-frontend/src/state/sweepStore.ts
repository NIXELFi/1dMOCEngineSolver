import { create } from "zustand";
import type { SweepSnapshot, SweepSummary, RpmState } from "../types/events";

export interface SweepStore {
  sweep: SweepSnapshot | null;
  availableSweeps: SweepSummary[];
  selectedRpm: number | null;
  // Per-RPM SimulationResults cache, keyed by `${sweep_id}:${rpm}`
  resultsCache: Record<string, unknown>;
  // WebSocket connection state
  connected: boolean;

  // Mutators
  setSnapshot: (sweep: SweepSnapshot | null, available: SweepSummary[]) => void;
  setSweep: (sweep: SweepSnapshot | null) => void;
  updateRpm: (rpm: number, partial: Partial<RpmState>) => void;
  setSelectedRpm: (rpm: number | null) => void;
  cacheResults: (sweepId: string, rpm: number, data: unknown) => void;
  setConnected: (c: boolean) => void;
}

export const useSweepStore = create<SweepStore>((set) => ({
  sweep: null,
  availableSweeps: [],
  selectedRpm: null,
  resultsCache: {},
  connected: false,

  setSnapshot: (sweep, available) =>
    set({ sweep, availableSweeps: available }),

  setSweep: (sweep) => set({ sweep }),

  updateRpm: (rpm, partial) =>
    set((state) => {
      if (!state.sweep) return state;
      const key = String(rpm);
      const existing = state.sweep.rpms[key] ?? state.sweep.rpms[String(Number(rpm))];
      if (!existing) return state;
      return {
        sweep: {
          ...state.sweep,
          rpms: {
            ...state.sweep.rpms,
            [key]: { ...existing, ...partial },
          },
        },
      };
    }),

  setSelectedRpm: (rpm) => set({ selectedRpm: rpm }),

  cacheResults: (sweepId, rpm, data) =>
    set((state) => ({
      resultsCache: {
        ...state.resultsCache,
        [`${sweepId}:${rpm}`]: data,
      },
    })),

  setConnected: (c) => set({ connected: c }),
}));
