import type { ServerMessage, SweepSnapshot } from "../types/events";
import { useSweepStore } from "./sweepStore";

/**
 * Normalize the rpms dict keys to JS-friendly form.
 *
 * The Python backend serializes rpm keys as e.g. "4500.0" because they
 * are float() in the LiveSweepState.rpms dict and Python's str(float)
 * produces the trailing .0. JavaScript's String(4500) is "4500" — no
 * trailing .0 — so direct lookups by `String(rpm)` would miss every
 * tile. We normalize on receive so the rest of the frontend can use
 * String(rpm) (4500 → "4500") consistently.
 */
function normalizeSweep(sweep: SweepSnapshot): SweepSnapshot {
  // For any rpm that's currently running but doesn't have a
  // client_started_at_ms (because we just received the snapshot from a
  // page reload, not from a live rpm_start event), back-fill the start
  // time from `Date.now() - elapsed * 1000`. This is accurate at the
  // moment of snapshot reception; the live ticker in WorkerTile then
  // counts up from there.
  const nowMs = Date.now();
  return {
    ...sweep,
    rpms: Object.fromEntries(
      Object.entries(sweep.rpms).map(([k, v]) => {
        const normalized = { ...v };
        if (
          normalized.status === "running" &&
          normalized.client_started_at_ms == null
        ) {
          const elapsedSec = normalized.elapsed ?? 0;
          normalized.client_started_at_ms = nowMs - elapsedSec * 1000;
        }
        return [String(Number(k)), normalized];
      })
    ),
    results_by_rpm_summary: Object.fromEntries(
      Object.entries(sweep.results_by_rpm_summary ?? {}).map(([k, v]) => [
        String(Number(k)),
        v,
      ])
    ),
  };
}

export function applyServerMessage(msg: ServerMessage): void {
  const store = useSweepStore.getState();

  switch (msg.type) {
    case "snapshot":
      store.setSnapshot(
        msg.sweep ? normalizeSweep(msg.sweep) : null,
        msg.available_sweeps
      );
      break;

    case "rpm_start":
      store.updateRpm(msg.rpm, {
        status: "running",
        current_cycle: 0,
        rpm_index: msg.rpm_index,
        delta_history: [],
        p_ivc_history: [],
        step_count: 0,
        elapsed: 0,
        client_started_at_ms: Date.now(),
      });
      break;

    case "cycle_done": {
      const current = store.sweep?.rpms[String(msg.rpm)];
      const newDeltaHist = [
        ...(current?.delta_history ?? []),
        msg.delta,
      ];
      const newPivcHist = [
        ...(current?.p_ivc_history ?? []),
        msg.p_ivc,
      ];
      store.updateRpm(msg.rpm, {
        current_cycle: msg.cycle,
        delta: msg.delta,
        delta_history: newDeltaHist,
        p_ivc_history: newPivcHist,
        step_count: msg.step_count,
        elapsed: msg.elapsed,
      });
      break;
    }

    case "converged":
      store.updateRpm(msg.rpm, { converged_at_cycle: msg.cycle });
      break;

    case "rpm_done":
      store.updateRpm(msg.rpm, {
        status: "done",
        perf: msg.perf,
        elapsed: msg.elapsed,
        step_count: msg.step_count,
        converged: msg.converged,
      });
      break;

    case "rpm_error":
      store.updateRpm(msg.rpm, {
        status: "error",
        error_type: msg.error_type,
        error_msg: msg.error_msg,
        traceback: msg.traceback,
      });
      break;

    case "sweep_complete":
      if (store.sweep) {
        store.setSweep({
          ...store.sweep,
          status: msg.stopped ? "stopped" : "complete",
        });
      }
      break;

    case "sweep_error":
      if (store.sweep) {
        store.setSweep({ ...store.sweep, status: "error" });
      }
      break;

    case "pong":
      // No-op
      break;
  }
}
