export type HeatmapMode =
  | 'waste_generation'
  | 'processing_gap'
  | 'waste_to_energy'
  | 'waste_composition';

export type GranularityView = 'state' | 'pincode';

export interface DataProvenance {
  source: string;
  reporting_period: string;
  agency: string;
  granularity: string;
  is_estimate: boolean;
  notes?: string;
}

export interface SolidWasteStats {
  data_available: boolean;
  reason?: string;
  generated_tpd?: number;
  collected_tpd?: number;
  treated_tpd?: number;
  processing_gap_tpd?: number;
  processing_gap_percentage?: number;
  collection_efficiency_pct?: number;
  treatment_efficiency_pct?: number;
  provenance?: DataProvenance;
}

export interface PlasticWasteStats {
  data_available: boolean;
  reason?: string;
  historical_tpy: Record<string, number | null>;
  latest_tpy?: number;
  latest_period?: string;
  trend?: string;
  provenance?: DataProvenance;
}

export interface WasteToEnergyStats {
  data_available: boolean;
  reason?: string;
  theoretical_power_mw?: number;
  treated_power_mw?: number;
  conversion_parameters: Record<string, any>;
  methodology: string;
  is_estimate: boolean;
  provenance?: DataProvenance;
}

export interface WasteCompositionStats {
  data_available: boolean;
  granularity: string;
  compostable_range_pct: [number, number];
  recyclable_range_pct: [number, number];
  inert_range_pct: [number, number];
  moisture_range_pct: [number, number];
  cn_ratio_range: [number, number];
  per_capita_generation_kg_day: [number, number];
  heavy_metals_mg_kg: Record<string, string>;
  limitations: string;
  provenance?: DataProvenance;
}

export interface CityStudyInfo {
  is_in_59_cities: boolean;
  city_name: string;
  waste_generation_rate?: string;
  specific_notes?: string;
  landfill_site?: string;
  lfg_flux_mg_m2_sec?: string;
  health_study_institution?: string;
}

export interface StateContextInfo {
  state_name: string;
  solid_waste?: SolidWasteStats;
  plastic_waste?: PlasticWasteStats;
  waste_to_energy?: WasteToEnergyStats;
}

export interface KarnatakaDistrictStats {
  has_district_data: boolean;
  district_name: string;
  state: string;
  reporting_period: string;
  source: string;
  geographic_level: string;
  metrics_unit: string;
  total_municipal_solid_waste_tpd?: number | null;
  wet_waste_generated_tpd?: number | null;
  dry_waste_generated_tpd?: number | null;
  drain_silt_inert_tpd?: number | null;
  construction_debris_tpd?: number | null;
  wet_waste_processed_tpd?: number | null;
  dry_waste_processed_tpd?: number | null;
  total_waste_processed_tpd?: number | null;
  city_compost_generated_tpd?: number | null;
  processing_gap_tpd?: number | null;
  processing_gap_percentage?: number | null;
  processing_efficiency_pct?: number | null;
}

export interface RegionDetails {
  identifier: string;
  name: string;
  region_type: 'state' | 'pincode' | 'city' | 'district';
  geographic_level?: string;
  pincode?: string;
  city?: string;
  office_name?: string;
  district?: string;
  state: string;
  circle?: string;
  division?: string;
  latitude?: number;
  longitude?: number;
  pincode_count?: number;
  data_integrity_notice: string;
  solid_waste: SolidWasteStats;
  plastic_waste: PlasticWasteStats;
  waste_to_energy: WasteToEnergyStats;
  waste_composition: WasteCompositionStats;
  state_context?: StateContextInfo;
  city_study?: CityStudyInfo;
  district_waste_stats?: KarnatakaDistrictStats | null;
}

export interface FilterOptions {
  modes: Array<{
    id: HeatmapMode;
    label: string;
    description: string;
    unit: string;
    icon: string;
  }>;
  views: Array<{
    id: GranularityView;
    label: string;
  }>;
  states: string[];
  districts_by_state: Record<string, string[]>;
  plastic_waste_years: string[];
}

export interface SearchResult {
  type: 'pincode' | 'city' | 'district' | 'state';
  id: string;
  title: string;
  subtitle: string;
  state: string;
  district?: string;
  city?: string;
  pincode?: string;
  pincode_count?: number;
  lat?: number;
  lon?: number;
  is_cpcb_studied?: boolean;
}

export interface SearchResponse {
  query: string;
  type: string;
  count: number;
  results: SearchResult[];
  error?: string | null;
}
