/**
 * TypeScript types mirroring the backend Pydantic schemas.
 * Source of truth: backend/app/schemas/simulation.py
 */

// ─── Request ─────────────────────────────────────────────────────────────────

export interface SimRequest {
  process?: string;
  location_id?: string | null;
  waste_mass_kg_day?: number | null;
  organic_fraction?: number | null;
  suitable_fraction?: number | null;
  use_ml_yield?: boolean;
  overrides?: Record<string, number>;
}

// ─── Results (mirrors SimResults) ────────────────────────────────────────────

export interface SimResults {
  // Mass flows [kg/day]
  organic_kg_d: number;
  suitable_kg_d: number;
  rejected_kg_d: number;
  water_added_kg_d: number;
  feed_kg_d: number;
  vs_kg_d: number;
  biogas_kg_d: number;
  digestate_kg_d: number;

  // Volumes / geometry
  digester_m3: number;
  biogas_nm3_d: number;
  ch4_nm3_d: number;

  // Per-VS metrics
  ch4_nm3_per_kg_vs: number;
  buswell_bound: number;
  vs_destruction: number;

  // Mass balance
  mass_residual_kg: number;

  // Energy [kWh/day]
  e_chem_kwh_d: number;
  flared_kwh_d: number;
  q_demand_kwh_d: number;
  q_feed_kwh_d: number;
  q_loss_kwh_d: number;
  boiler_chem_kwh_d: number;
  chp_chem_kwh_d: number;
  e_gross_kwh_d: number;
  aux_kwh_d: number;
  e_net_kwh_d: number;
  heat_surplus_kwh_d: number;

  // Flags / metadata
  heat_deficit: boolean;
  out_of_range_inputs: string[];
  warnings: string[];
  /**
   * Either "illustrative_estimate" or "extrapolation".
   * This value is hoisted to SimResponse.status as well.
   */
  status: "illustrative_estimate" | "extrapolation" | string;
}

// ─── Rule warning ─────────────────────────────────────────────────────────────

export interface RuleWarning {
  code: string;
  severity: string;
  stage: string;
  message: string;
  basis: string;
}

// ─── Response (mirrors SimResponse) ─────────────────────────────────────────

export interface SimResponse {
  id: string;
  inputs: Record<string, unknown>;
  params: Record<string, unknown>;
  results: SimResults;
  notes: Record<string, unknown>;
  model_version: string;
  audit_hash: string;
  /**
   * Top-level status hoisted from results.status.
   * "illustrative_estimate" | "extrapolation"
   */
  status: "illustrative_estimate" | "extrapolation" | string;
  defaults_used_unvalidated: string[];
  warnings_detail: RuleWarning[];
  missing_inputs: string[];
}

// ─── API error shape ──────────────────────────────────────────────────────────

export interface ApiError {
  detail: string | Array<{ loc: string[]; msg: string; type: string }>;
}
