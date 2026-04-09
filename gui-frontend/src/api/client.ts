import type { SweepSummary } from "../types/events";
import type { EngineConfigPayload } from "../state/configStore";
export type { EngineConfigPayload };

const BASE = ""; // same origin (FastAPI serves both static + api)

export interface ConfigSummary {
  name: string;
  path: string;
  summary: string;
}

export interface ApiFieldError {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface ApiValidationError {
  status: 422;
  fieldErrors: Record<string, string>;
}

export interface StartSweepParams {
  rpm_start: number;
  rpm_end: number;
  rpm_step: number;
  n_cycles: number;
  n_workers: number;
  config_name: string;
}

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${url}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch {
      // body wasn't JSON
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

function parseFieldErrors(detail: ApiFieldError[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const entry of detail) {
    // loc is e.g. ["body", "intake_valve", "cd_table", 0, 0]
    // skip the leading "body" segment
    const path = entry.loc
      .slice(1)
      .map((p) => String(p))
      .join(".");
    out[path] = entry.msg;
  }
  return out;
}

async function jsonFetchWithFieldErrors<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${BASE}${url}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (response.status === 422) {
    const body = await response.json();
    const err = new Error("Validation failed") as Error & {
      fieldErrors: Record<string, string>;
      status: number;
    };
    err.fieldErrors = parseFieldErrors(body.detail ?? []);
    err.status = 422;
    throw err;
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch {
      // body wasn't JSON
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => jsonFetch<{ status: string }>("/api/health"),

  listConfigs: () => jsonFetch<ConfigSummary[]>("/api/configs"),

  listSweeps: () => jsonFetch<SweepSummary[]>("/api/sweeps"),

  loadSweep: (id: string) =>
    jsonFetch<unknown>(`/api/sweeps/${encodeURIComponent(id)}`),

  startSweep: (params: StartSweepParams) =>
    jsonFetch<{ sweep_id: string; status: string }>("/api/sweep/start", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  stopSweep: () =>
    jsonFetch<{ status: string }>("/api/sweep/stop", { method: "POST" }),

  getCurrentResults: (rpm: number) =>
    jsonFetch<unknown>(`/api/sweeps/current/results/${rpm}`),

  getConfig: (name: string) =>
    jsonFetch<EngineConfigPayload>(`/api/configs/${encodeURIComponent(name)}`),

  saveConfig: (name: string, payload: EngineConfigPayload) =>
    jsonFetchWithFieldErrors<EngineConfigPayload>(
      `/api/configs/${encodeURIComponent(name)}`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      },
    ),

  saveConfigAs: (name: string, payload: EngineConfigPayload) =>
    jsonFetchWithFieldErrors<EngineConfigPayload>(`/api/configs`, {
      method: "POST",
      body: JSON.stringify({ name, payload }),
    }),
};
