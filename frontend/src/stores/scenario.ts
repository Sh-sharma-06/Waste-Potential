/**
 * Zustand store for the active simulation scenario.
 *
 * Holds the current form inputs, the last API response, loading state, and
 * any error message.  Consumed by the SimulatorPage and any child component
 * that needs access to `result.status` for the dynamic badge.
 */

import { create } from "zustand";
import type { SimRequest, SimResponse } from "@/lib/api/api.d";
import { postSimulation } from "@/lib/api/client";

// ─── State shape ─────────────────────────────────────────────────────────────

export interface ScenarioForm {
  waste_mass_kg_day: number;
  organic_fraction: number;
  suitable_fraction: number;
  location_id: string;
}

export interface ScenarioState {
  /** Current form values */
  form: ScenarioForm;
  /** Last successful SimResponse from POST /simulations */
  result: SimResponse | null;
  /** True while an API call is in flight */
  loading: boolean;
  /** Error message from the last failed call, or null */
  error: string | null;

  /** Update one or more form fields */
  setForm: (patch: Partial<ScenarioForm>) => void;
  /** POST /simulations with the current form values */
  runSimulation: () => Promise<void>;
  /** Clear last result and error */
  reset: () => void;
}

// ─── Default form values ──────────────────────────────────────────────────────

const DEFAULT_FORM: ScenarioForm = {
  waste_mass_kg_day: 1000,
  organic_fraction: 0.55,
  suitable_fraction: 0.8,
  location_id: "",
};

// ─── Store ────────────────────────────────────────────────────────────────────

export const useScenarioStore = create<ScenarioState>((set, get) => ({
  form: { ...DEFAULT_FORM },
  result: null,
  loading: false,
  error: null,

  setForm(patch) {
    set((s) => ({ form: { ...s.form, ...patch } }));
  },

  async runSimulation() {
    const { form } = get();
    set({ loading: true, error: null });

    const body: SimRequest = {
      process: "anaerobic_digestion",
      waste_mass_kg_day: form.waste_mass_kg_day,
      organic_fraction: form.organic_fraction,
      suitable_fraction: form.suitable_fraction,
      ...(form.location_id.trim() ? { location_id: form.location_id.trim() } : {}),
    };

    try {
      const response = await postSimulation(body);
      // Guard: status should always be present but default gracefully.
      if (!response.status) {
        (response as SimResponse & { status: string }).status =
          response.results?.status ?? "illustrative_estimate";
      }
      set({ result: response, loading: false });
    } catch (err) {
      set({
        loading: false,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  },

  reset() {
    set({ result: null, error: null });
  },
}));
