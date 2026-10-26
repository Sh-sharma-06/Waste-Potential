import React, { useState } from 'react';
import type { RegionDetails, HeatmapMode } from '../types';
import {
  X,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  AlertTriangle,
  Zap,
  PieChart,
  Calendar,
  Building2,
  MapPin,
  ChevronDown,
  ChevronUp,
  Info,
  Flame,
  Sparkles,
} from 'lucide-react';

interface DetailsPanelProps {
  details: RegionDetails | null;
  onClose: () => void;
  activeMode: HeatmapMode;
  isLoading: boolean;
}

export const DetailsPanel: React.FC<DetailsPanelProps> = ({
  details,
  onClose,
  activeMode,
  isLoading,
}) => {
  const [showWteFormula, setShowWteFormula] = useState(false);

  if (isLoading) {
    return (
      <div className="bg-white/95 backdrop-blur-md rounded-2xl border border-slate-200/90 shadow-sm p-6 flex flex-col items-center justify-center min-h-[350px]">
        <div className="w-8 h-8 border-3 border-emerald-600 border-t-transparent rounded-full animate-spin mb-3" />
        <span className="text-xs font-semibold text-slate-700">Loading location intelligence...</span>
      </div>
    );
  }

  if (!details) {
    return (
      <div className="bg-white/95 backdrop-blur-md rounded-2xl border border-slate-200/90 shadow-sm p-6 text-center space-y-3">
        <div className="w-12 h-12 rounded-2xl bg-slate-100 flex items-center justify-center text-slate-400 mx-auto">
          <MapPin className="w-6 h-6" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-slate-800">No Location Selected</h3>
          <p className="text-xs text-slate-500 max-w-xs mx-auto mt-1">
            Search by PIN code, City, or District above, or click any boundary on the interactive map to inspect verified waste statistics.
          </p>
        </div>
      </div>
    );
  }

  const isPincode = details.region_type === 'pincode';
  const isCity = details.region_type === 'city';
  const isDistrict = details.region_type === 'district';
  const isState = details.region_type === 'state';

  // For PIN code: use state_context for macro figures while keeping PIN stats explicitly unavailable
  const displaySolid = isPincode && details.state_context?.solid_waste
    ? details.state_context.solid_waste
    : details.solid_waste;

  const displayPlastic = isPincode && details.state_context?.plastic_waste
    ? details.state_context.plastic_waste
    : details.plastic_waste;

  const displayWte = isPincode && details.state_context?.waste_to_energy
    ? details.state_context.waste_to_energy
    : details.waste_to_energy;

  const comp = details.waste_composition;
  const cityStudy = details.city_study;

  // Geographic level badge configuration
  const levelBadge = isPincode
    ? { label: 'Postal PIN Code Area', color: 'bg-amber-100 text-amber-800 border-amber-300' }
    : isCity
    ? { label: 'City / Urban Area', color: 'bg-teal-100 text-teal-800 border-teal-300' }
    : isDistrict
    ? { label: 'District Administrative Area', color: 'bg-indigo-100 text-indigo-800 border-indigo-300' }
    : { label: 'State / Union Territory', color: 'bg-emerald-100 text-emerald-800 border-emerald-300' };

  return (
    <div className="bg-white/95 backdrop-blur-md rounded-2xl border border-slate-200/90 shadow-sm overflow-hidden flex flex-col max-h-[85vh]">
      {/* Header */}
      <div className="p-4 border-b border-slate-200/80 bg-slate-50/50 flex items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span
              className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider border ${levelBadge.color}`}
            >
              {levelBadge.label}
            </span>
            {details.pincode && (
              <span className="text-xs text-slate-600 font-mono font-semibold bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                PIN: {details.pincode}
              </span>
            )}
            {details.pincode_count && details.pincode_count > 1 && (
              <span className="text-[11px] text-slate-500 font-medium">
                ({details.pincode_count.toLocaleString()} PIN delivery areas)
              </span>
            )}
          </div>

          <h2 className="text-base font-bold text-slate-900 leading-tight">
            {details.name}
          </h2>

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500 mt-1">
            {details.district && (
              <span className="flex items-center gap-1">
                <Building2 className="w-3 h-3 text-slate-400" /> District: {details.district}
              </span>
            )}
            <span className="flex items-center gap-1 font-medium text-slate-700">
              <MapPin className="w-3 h-3 text-emerald-600" /> State: {details.state}
            </span>
            {details.office_name && details.office_name !== details.name && (
              <span className="text-[11px] text-slate-400">
                PO: {details.office_name}
              </span>
            )}
            {details.latitude !== null && details.latitude !== undefined && details.longitude !== null && details.longitude !== undefined && (
              <span className="text-[10px] text-slate-400 font-mono">
                [{details.latitude.toFixed(4)}°N, {details.longitude.toFixed(4)}°E]
              </span>
            )}
          </div>
        </div>

        <button
          onClick={onClose}
          className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-200/80 rounded-lg transition-colors"
          title="Close Panel"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Scrollable Content */}
      <div className="p-4 space-y-3.5 overflow-y-auto flex-1">
        {/* Data Integrity Notice Banner */}
        <div
          className={`p-3 rounded-xl border flex items-start gap-2.5 text-xs ${
            isPincode
              ? 'bg-amber-50/90 border-amber-200 text-amber-900'
              : isCity || isDistrict
              ? 'bg-sky-50/90 border-sky-200 text-sky-900'
              : 'bg-emerald-50/90 border-emerald-200 text-emerald-900'
          }`}
        >
          {isPincode ? (
            <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          ) : isCity || isDistrict ? (
            <Info className="w-4 h-4 text-sky-600 shrink-0 mt-0.5" />
          ) : (
            <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
          )}
          <div className="leading-relaxed text-[11px]">
            {details.data_integrity_notice}
          </div>
        </div>

        {/* --- CPCB 59-CITY STUDY CARD (When city study metadata exists) --- */}
        {cityStudy && (
          <div className="rounded-xl border border-teal-200 bg-teal-50/40 p-3.5 space-y-2.5 shadow-xs">
            <div className="flex items-center justify-between border-b border-teal-100 pb-2">
              <span className="text-xs font-bold text-teal-900 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-teal-700" />
                <span>CPCB 59-City Study Intelligence</span>
              </span>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-teal-100 text-teal-800">
                City Study
              </span>
            </div>

            <div className="space-y-1.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-slate-600 font-medium">Waste Generation Rate:</span>
                <span className="font-bold text-teal-900">
                  {cityStudy.waste_generation_rate || '0.12 - 0.60 kg/capita/day'}
                </span>
              </div>

              {cityStudy.landfill_site && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-600 font-medium">Disposal / Landfill Site:</span>
                  <span className="font-semibold text-slate-800">{cityStudy.landfill_site}</span>
                </div>
              )}

              {cityStudy.lfg_flux_mg_m2_sec && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-600 font-medium flex items-center gap-1">
                    <Flame className="w-3 h-3 text-amber-600" /> Landfill Gas (LFG) Flux:
                  </span>
                  <span className="font-bold text-amber-900 font-mono">
                    {cityStudy.lfg_flux_mg_m2_sec} mg/m²/sec
                  </span>
                </div>
              )}

              {cityStudy.specific_notes && (
                <div className="text-[11px] text-slate-600 pt-1.5 border-t border-teal-100 leading-relaxed italic">
                  {cityStudy.specific_notes}
                </div>
              )}
            </div>
          </div>
        )}

        {/* --- VERIFIED DISTRICT SOLID WASTE & PROCESSING (DMA KARNATAKA) --- */}
        {details.district_waste_stats && (
          <div className="rounded-xl border border-blue-200 bg-blue-50/40 p-3.5 space-y-3 shadow-xs">
            <div className="flex items-center justify-between border-b border-blue-100 pb-2">
              <span className="text-xs font-bold text-blue-950 flex items-center gap-1.5">
                <Building2 className="w-3.5 h-3.5 text-blue-700" />
                <span>Verified District Waste & Processing (DMA Karnataka)</span>
              </span>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-blue-100 text-blue-800 border border-blue-200">
                District Level Data
              </span>
            </div>

            {/* District Metadata / Provenance Notice */}
            <div className="text-[10px] text-blue-900 bg-white/80 p-2.5 rounded-lg border border-blue-100 space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-700">Administrative Unit:</span>
                <span className="font-bold text-blue-950">{details.district_waste_stats.district_name}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-700">Source:</span>
                <span className="text-slate-600 text-right">{details.district_waste_stats.source}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-700">Reporting Period:</span>
                <span className="text-slate-600 font-medium">{details.district_waste_stats.reporting_period}</span>
              </div>
              <div className="text-[9.5px] text-blue-800 pt-1 border-t border-blue-100/70 italic">
                Verified district-level measurements. Statistics reflect the district administrative area and are not uniformly disaggregated across individual postal PIN codes.
              </div>
            </div>

            {/* Metrics Grid */}
            <div className="grid grid-cols-2 gap-2">
              <div className="p-2 rounded-lg bg-white border border-blue-100 shadow-2xs">
                <span className="text-[9.5px] text-slate-500 block uppercase font-medium">
                  Total MSW Generated
                </span>
                <span className="text-sm font-bold text-blue-950">
                  {details.district_waste_stats.total_municipal_solid_waste_tpd !== null && details.district_waste_stats.total_municipal_solid_waste_tpd !== undefined
                    ? `${details.district_waste_stats.total_municipal_solid_waste_tpd.toLocaleString()} TPD`
                    : 'N/A'}
                </span>
              </div>

              <div className="p-2 rounded-lg bg-white border border-blue-100 shadow-2xs">
                <span className="text-[9.5px] text-slate-500 block uppercase font-medium">
                  Total Waste Processed
                </span>
                <span className="text-sm font-bold text-emerald-700">
                  {details.district_waste_stats.total_waste_processed_tpd !== null && details.district_waste_stats.total_waste_processed_tpd !== undefined
                    ? `${details.district_waste_stats.total_waste_processed_tpd.toLocaleString()} TPD`
                    : 'N/A'}
                </span>
                {details.district_waste_stats.processing_efficiency_pct !== null && details.district_waste_stats.processing_efficiency_pct !== undefined && (
                  <span className="text-[9.5px] text-emerald-600 font-semibold block">
                    {details.district_waste_stats.processing_efficiency_pct}% efficiency
                  </span>
                )}
              </div>

              <div className="p-2 rounded-lg bg-white border border-blue-100 shadow-2xs">
                <span className="text-[9.5px] text-slate-500 block uppercase font-medium">
                  Wet Waste Generated
                </span>
                <span className="text-xs font-bold text-slate-800">
                  {details.district_waste_stats.wet_waste_generated_tpd !== null && details.district_waste_stats.wet_waste_generated_tpd !== undefined
                    ? `${details.district_waste_stats.wet_waste_generated_tpd.toLocaleString()} TPD`
                    : 'N/A'}
                </span>
                {details.district_waste_stats.wet_waste_processed_tpd !== null && details.district_waste_stats.wet_waste_processed_tpd !== undefined && (
                  <span className="text-[9px] text-slate-500 block">
                    Proc: {details.district_waste_stats.wet_waste_processed_tpd.toLocaleString()} TPD
                  </span>
                )}
              </div>

              <div className="p-2 rounded-lg bg-white border border-blue-100 shadow-2xs">
                <span className="text-[9.5px] text-slate-500 block uppercase font-medium">
                  Dry Waste Generated
                </span>
                <span className="text-xs font-bold text-slate-800">
                  {details.district_waste_stats.dry_waste_generated_tpd !== null && details.district_waste_stats.dry_waste_generated_tpd !== undefined
                    ? `${details.district_waste_stats.dry_waste_generated_tpd.toLocaleString()} TPD`
                    : 'N/A'}
                </span>
                {details.district_waste_stats.dry_waste_processed_tpd !== null && details.district_waste_stats.dry_waste_processed_tpd !== undefined && (
                  <span className="text-[9px] text-slate-500 block">
                    Proc: {details.district_waste_stats.dry_waste_processed_tpd.toLocaleString()} TPD
                  </span>
                )}
              </div>

              {details.district_waste_stats.drain_silt_inert_tpd !== null && details.district_waste_stats.drain_silt_inert_tpd !== undefined && (
                <div className="p-2 rounded-lg bg-white border border-blue-100 shadow-2xs">
                  <span className="text-[9.5px] text-slate-500 block uppercase font-medium">
                    Drain Silt & Inert
                  </span>
                  <span className="text-xs font-bold text-slate-800">
                    {details.district_waste_stats.drain_silt_inert_tpd.toLocaleString()} TPD
                  </span>
                </div>
              )}

              {details.district_waste_stats.construction_debris_tpd !== null && details.district_waste_stats.construction_debris_tpd !== undefined && (
                <div className="p-2 rounded-lg bg-white border border-blue-100 shadow-2xs">
                  <span className="text-[9.5px] text-slate-500 block uppercase font-medium">
                    C&D Waste
                  </span>
                  <span className="text-xs font-bold text-slate-800">
                    {details.district_waste_stats.construction_debris_tpd.toLocaleString()} TPD
                  </span>
                </div>
              )}

              {details.district_waste_stats.city_compost_generated_tpd !== null && details.district_waste_stats.city_compost_generated_tpd !== undefined && (
                <div className="p-2 rounded-lg bg-white border border-blue-100 shadow-2xs">
                  <span className="text-[9.5px] text-slate-500 block uppercase font-medium">
                    City Compost Produced
                  </span>
                  <span className="text-xs font-bold text-emerald-800">
                    {details.district_waste_stats.city_compost_generated_tpd.toLocaleString()} TPD
                  </span>
                </div>
              )}

              {details.district_waste_stats.processing_gap_tpd !== null && details.district_waste_stats.processing_gap_tpd !== undefined && (
                <div className="p-2 rounded-lg bg-amber-50/80 border border-amber-200 shadow-2xs">
                  <span className="text-[9.5px] text-amber-800 block uppercase font-medium">
                    District Processing Gap
                  </span>
                  <span className="text-xs font-bold text-amber-950">
                    {details.district_waste_stats.processing_gap_tpd.toLocaleString()} TPD
                  </span>
                  {details.district_waste_stats.processing_gap_percentage !== null && details.district_waste_stats.processing_gap_percentage !== undefined && (
                    <span className="text-[9px] text-amber-700 font-semibold block">
                      {details.district_waste_stats.processing_gap_percentage}% of district MSW
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* --- 1. Municipal Solid Waste Overview Card --- */}
        <div
          className={`rounded-xl border bg-white p-3.5 space-y-3 transition-all ${
            activeMode === 'waste_generation' || activeMode === 'processing_gap'
              ? 'border-emerald-500 shadow-xs ring-1 ring-emerald-500/30'
              : 'border-slate-200'
          }`}
        >
          <div className="flex items-center justify-between border-b border-slate-100 pb-2">
            <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
              <Trash2 className="w-3.5 h-3.5 text-emerald-600" /> Municipal Solid Waste
            </span>
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-600">
              {isState
                ? 'Reported 2020-21 (State Level)'
                : `State Context (${details.state})`}
            </span>
          </div>

          {/* Granularity Label Warning */}
          {!isState && (
            <div className="text-[10px] text-slate-500 bg-slate-50 p-1.5 rounded-lg border border-slate-100">
              <span className="font-semibold text-slate-700">Geographic Level:</span> State-Level Measurement for{' '}
              <span className="font-semibold text-slate-900">{details.state}</span> (not localized {levelBadge.label} figures).
            </div>
          )}

          <div className="grid grid-cols-2 gap-2.5">
            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
              <span className="text-[10px] text-slate-500 block uppercase font-medium">
                Generated
              </span>
              <span className="text-base font-bold text-slate-900">
                {displaySolid?.generated_tpd !== null && displaySolid?.generated_tpd !== undefined
                  ? `${displaySolid.generated_tpd.toLocaleString()} TPD`
                  : 'N/A'}
              </span>
            </div>

            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
              <span className="text-[10px] text-slate-500 block uppercase font-medium">
                Collected
              </span>
              <span className="text-base font-bold text-slate-900">
                {displaySolid?.collected_tpd !== null && displaySolid?.collected_tpd !== undefined
                  ? `${displaySolid.collected_tpd.toLocaleString()} TPD`
                  : 'N/A'}
              </span>
              {displaySolid?.collection_efficiency_pct !== null && displaySolid?.collection_efficiency_pct !== undefined && (
                <span className="text-[10px] text-emerald-600 font-medium block">
                  {displaySolid.collection_efficiency_pct}% efficiency
                </span>
              )}
            </div>

            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
              <span className="text-[10px] text-slate-500 block uppercase font-medium">
                Treated
              </span>
              <span className="text-base font-bold text-slate-900">
                {displaySolid?.treated_tpd !== null && displaySolid?.treated_tpd !== undefined
                  ? `${displaySolid.treated_tpd.toLocaleString()} TPD`
                  : 'Not Available'}
              </span>
              {displaySolid?.treatment_efficiency_pct !== null && displaySolid?.treatment_efficiency_pct !== undefined && (
                <span className="text-[10px] text-emerald-600 font-medium block">
                  {displaySolid.treatment_efficiency_pct}% treated
                </span>
              )}
            </div>

            <div className="p-2.5 rounded-lg bg-amber-50/60 border border-amber-200/70">
              <span className="text-[10px] text-amber-800 block uppercase font-medium flex items-center gap-1">
                <AlertTriangle className="w-3 h-3 text-amber-600" /> Processing Gap
              </span>
              <span className="text-base font-bold text-amber-950">
                {displaySolid?.processing_gap_tpd !== null && displaySolid?.processing_gap_tpd !== undefined
                  ? `${displaySolid.processing_gap_tpd.toLocaleString()} TPD`
                  : 'N/A'}
              </span>
              {displaySolid?.processing_gap_percentage !== null && displaySolid?.processing_gap_percentage !== undefined && (
                <span className="text-[10px] text-amber-700 font-medium block">
                  {displaySolid.processing_gap_percentage}% unprocessed
                </span>
              )}
            </div>
          </div>
        </div>

        {/* --- 2. Plastic Waste Historical Series Card --- */}
        <div className="rounded-xl border border-slate-200 bg-white p-3.5 space-y-2.5">
          <div className="flex items-center justify-between border-b border-slate-100 pb-2">
            <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5 text-blue-600" /> Plastic Waste Trend (TPY)
            </span>
            {displayPlastic?.trend && (
              <span className="text-[10px] font-semibold text-blue-700">
                {displayPlastic.trend}
              </span>
            )}
          </div>

          {!isState && (
            <div className="text-[10px] text-slate-500">
              Parent State measurement for <span className="font-semibold text-slate-700">{details.state}</span>:
            </div>
          )}

          {displayPlastic?.data_available && displayPlastic?.historical_tpy && Object.keys(displayPlastic.historical_tpy).length > 0 ? (
            <div className="space-y-1.5 pt-1">
              {Object.entries(displayPlastic.historical_tpy).map(([yr, val]) => (
                <div key={yr} className="flex items-center justify-between text-xs py-0.5">
                  <span className="text-slate-600 font-medium">{yr}:</span>
                  <span className="font-bold text-slate-800">
                    {val !== null ? `${val.toLocaleString()} TPY` : 'NA'}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-slate-500 py-1 italic">
              {displayPlastic?.reason || 'Plastic waste generation data unavailable for this state.'}
            </div>
          )}
        </div>

        {/* --- 3. Waste-to-Energy Potential Card --- */}
        <div className="rounded-xl border border-slate-200 bg-white p-3.5 space-y-2.5">
          <div className="flex items-center justify-between border-b border-slate-100 pb-2">
            <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5 text-indigo-600" /> Waste-to-Energy Potential
            </span>
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-indigo-50 text-indigo-700">
              MNRE Combustion Model
            </span>
          </div>

          {!isState && (
            <div className="text-[10px] text-slate-500">
              Calculated for parent state <span className="font-semibold text-slate-700">{details.state}</span>:
            </div>
          )}

          {displayWte?.data_available ? (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <div className="p-2.5 rounded-lg bg-indigo-50/50 border border-indigo-100">
                  <span className="text-[10px] text-slate-500 block uppercase font-medium">
                    Theoretical Power
                  </span>
                  <span className="text-base font-bold text-indigo-900">
                    {displayWte.theoretical_power_mw} MW
                  </span>
                  <span className="text-[10px] text-slate-500 block">From total MSW</span>
                </div>

                <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                  <span className="text-[10px] text-slate-500 block uppercase font-medium">
                    Treated Feedstock
                  </span>
                  <span className="text-base font-bold text-slate-800">
                    {displayWte.treated_power_mw !== null ? `${displayWte.treated_power_mw} MW` : 'N/A'}
                  </span>
                  <span className="text-[10px] text-slate-500 block">From treated MSW</span>
                </div>
              </div>

              {/* Conversion Parameters Dropdown */}
              <div>
                <button
                  onClick={() => setShowWteFormula(!showWteFormula)}
                  className="w-full flex items-center justify-between text-[11px] text-slate-600 hover:text-slate-900 p-1.5 rounded-lg hover:bg-slate-50 transition-colors"
                >
                  <span className="font-medium">Calculation Parameters & Formula</span>
                  {showWteFormula ? (
                    <ChevronUp className="w-3.5 h-3.5" />
                  ) : (
                    <ChevronDown className="w-3.5 h-3.5" />
                  )}
                </button>

                {showWteFormula && (
                  <div className="p-2.5 mt-1 bg-slate-50 rounded-lg text-[11px] text-slate-600 space-y-1.5 border border-slate-200">
                    <p className="font-mono text-[10px] bg-white p-1 rounded border border-slate-200">
                      Power (MW) = (Waste_TPD × 0.20 × 1,100 × 0.22) / (24 × 860)
                    </p>
                    <ul className="list-disc list-inside space-y-0.5 text-[10px] text-slate-500">
                      <li>Combustible fraction: 20% (CPCB 59-city study)</li>
                      <li>Net Calorific Value: 1,100 kcal/kg (Indian MSW standard)</li>
                      <li>Plant efficiency: 22% thermal-to-electric</li>
                      <li>Effective factor: ~0.002345 MW per Ton Per Day</li>
                    </ul>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="p-2.5 bg-slate-50 rounded-lg text-xs text-slate-600 border border-slate-200">
              <span className="font-semibold block text-slate-800 mb-1">Calculation Withheld:</span>
              {displayWte?.reason || 'Waste-to-energy potential withheld due to lack of local generation figures.'}
            </div>
          )}
        </div>

        {/* --- 4. Physical Waste Composition Card --- */}
        <div className="rounded-xl border border-slate-200 bg-white p-3.5 space-y-2.5">
          <div className="flex items-center justify-between border-b border-slate-100 pb-2">
            <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
              <PieChart className="w-3.5 h-3.5 text-teal-600" /> Physical Waste Composition
            </span>
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-teal-50 text-teal-700">
              CPCB 59-City Study
            </span>
          </div>

          <div className="space-y-2">
            <div>
              <div className="flex justify-between text-xs text-slate-700 mb-1">
                <span>Compostable / Biodegradable:</span>
                <span className="font-bold text-teal-700">
                  {comp.compostable_range_pct[0]}% - {comp.compostable_range_pct[1]}%
                </span>
              </div>
              <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                <div className="h-full bg-teal-500 rounded-full w-[50%]" />
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs text-slate-700 mb-1">
                <span>Recyclable (Paper, Plastics, Metals):</span>
                <span className="font-bold text-teal-700">
                  {comp.recyclable_range_pct[0]}% - {comp.recyclable_range_pct[1]}%
                </span>
              </div>
              <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                <div className="h-full bg-teal-400 rounded-full w-[20%]" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 pt-1 text-[11px] text-slate-600">
              <div className="p-2 rounded bg-slate-50 border border-slate-100">
                <span className="text-[10px] text-slate-400 block uppercase">Moisture Content</span>
                <span className="font-bold text-slate-800">
                  {comp.moisture_range_pct[0]}% - {comp.moisture_range_pct[1]}%
                </span>
              </div>
              <div className="p-2 rounded bg-slate-50 border border-slate-100">
                <span className="text-[10px] text-slate-400 block uppercase">C:N Ratio</span>
                <span className="font-bold text-slate-800">
                  {comp.cn_ratio_range[0]} - {comp.cn_ratio_range[1]}
                </span>
              </div>
            </div>

            <div className="text-[10px] text-slate-500 italic pt-1 border-t border-slate-100">
              {comp.limitations}
            </div>
          </div>
        </div>

        {/* --- 5. Data Provenance & Reporting Period Footer --- */}
        <div className="p-3 bg-slate-50 rounded-xl border border-slate-200/80 text-[11px] text-slate-500 space-y-1">
          <div className="font-semibold text-slate-700 flex items-center gap-1">
            <Info className="w-3 h-3 text-slate-400" /> Data Provenance & Coverage
          </div>
          <div><span className="font-medium text-slate-600">Geographic Level:</span> {levelBadge.label}</div>
          <div><span className="font-medium text-slate-600">Primary Source:</span> Central Pollution Control Board (CPCB)</div>
          <div><span className="font-medium text-slate-600">Reporting Periods:</span> Solid Waste (2020-21), Plastic Waste (2018-2023), Waste Composition (59-City Study)</div>
          <div><span className="font-medium text-slate-600">Spatial Directory:</span> India Post / Open Government Data Platform India</div>
        </div>
      </div>
    </div>
  );
};

export default DetailsPanel;
