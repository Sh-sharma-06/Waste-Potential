import React, { useState } from 'react';
import {
  X,
  Database,
  Calculator,
  ShieldAlert,
  FileText,
  Layers,
  CheckCircle,
  Zap,
  PieChart,
} from 'lucide-react';

interface InfoModalProps {
  isOpen: boolean;
  onClose: () => void;
  sourcesData: any;
  methodologyData: any;
}

export const InfoModal: React.FC<InfoModalProps> = ({
  isOpen,
  onClose,
  sourcesData,
  methodologyData,
}) => {
  const [activeTab, setActiveTab] = useState<'sources' | 'methodology' | 'integrity'>('sources');

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fadeIn">
      <div className="bg-white rounded-3xl border border-slate-200/90 shadow-2xl w-full max-w-3xl max-h-[85vh] overflow-hidden flex flex-col">
        {/* Modal Header */}
        <div className="p-5 border-b border-slate-200/80 bg-slate-50 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-600 flex items-center justify-center text-white shadow-md shadow-emerald-600/20">
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">
                Sources, Methodology & Data Integrity
              </h2>
              <p className="text-xs text-slate-500">
                Documentation of datasets, calculation parameters, and geospatial standards.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-slate-700 hover:bg-slate-200/80 rounded-xl transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Buttons */}
        <div className="flex border-b border-slate-200 bg-slate-50/50 px-5 gap-4">
          <button
            onClick={() => setActiveTab('sources')}
            className={`py-3 text-xs font-bold border-b-2 transition-all flex items-center gap-1.5 ${
              activeTab === 'sources'
                ? 'border-emerald-600 text-emerald-800'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Database className="w-4 h-4" /> Data Sources (5 Datasets)
          </button>
          <button
            onClick={() => setActiveTab('methodology')}
            className={`py-3 text-xs font-bold border-b-2 transition-all flex items-center gap-1.5 ${
              activeTab === 'methodology'
                ? 'border-emerald-600 text-emerald-800'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Calculator className="w-4 h-4" /> Calculation Methodology
          </button>
          <button
            onClick={() => setActiveTab('integrity')}
            className={`py-3 text-xs font-bold border-b-2 transition-all flex items-center gap-1.5 ${
              activeTab === 'integrity'
                ? 'border-emerald-600 text-emerald-800'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <ShieldAlert className="w-4 h-4" /> Integrity & Limitations
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-4 text-xs text-slate-600 flex-1">
          {/* TAB 1: Sources */}
          {activeTab === 'sources' && (
            <div className="space-y-4">
              <p className="text-slate-600 leading-relaxed">
                The platform runs strictly on verified, real data from official Government of India bodies.
                No mock data, synthetic values, or fabricated statistics are used anywhere in this application.
              </p>

              <div className="space-y-3">
                {sourcesData?.datasets?.map((ds: any) => (
                  <div
                    key={ds.id}
                    className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/60 hover:bg-slate-50 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2 mb-1.5">
                      <h4 className="font-bold text-slate-900 text-xs flex items-center gap-2">
                        <CheckCircle className="w-4 h-4 text-emerald-600" />
                        {ds.name}
                      </h4>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white border border-slate-200 text-slate-600">
                        {ds.file}
                      </span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-slate-600 mb-2">
                      <div>
                        <span className="text-slate-400">Authority:</span> {ds.publishing_body}
                      </div>
                      <div>
                        <span className="text-slate-400">Reporting Period:</span> {ds.reporting_period}
                      </div>
                      <div>
                        <span className="text-slate-400">Coverage:</span> {ds.coverage}
                      </div>
                      <div>
                        <span className="text-slate-400">Granularity:</span> {ds.granularity}
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {ds.metrics?.map((m: string, i: number) => (
                        <span
                          key={i}
                          className="px-2 py-0.5 rounded-md bg-emerald-50 border border-emerald-200 text-emerald-800 text-[10px] font-medium"
                        >
                          {m}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 2: Methodology */}
          {activeTab === 'methodology' && (
            <div className="space-y-5">
              {/* Processing Gap */}
              <div className="p-4 rounded-xl border border-slate-200 bg-white space-y-2">
                <h4 className="font-bold text-slate-900 text-xs flex items-center gap-1.5">
                  <Calculator className="w-4 h-4 text-amber-600" />
                  1. Unprocessed Waste Gap Calculation
                </h4>
                <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200 font-mono text-[11px] text-slate-800">
                  Processing Gap (TPD) = Solid Waste Generated (TPD) - Treated (TPD)
                </div>
                <p className="text-[11px] text-slate-600">
                  The processing gap represents the volume of uncollected or untreated municipal solid waste that ends up in open dumpsites, unlined landfills, or water bodies daily.
                  Collection and treatment efficiencies are computed as ratios of total reported generation.
                  Where CPCB indicates 'NA' for treated tonnage (e.g. Arunachal Pradesh, Bihar), the gap is explicitly declared unavailable.
                </p>
              </div>

              {/* Waste to Energy */}
              <div className="p-4 rounded-xl border border-slate-200 bg-white space-y-2">
                <h4 className="font-bold text-slate-900 text-xs flex items-center gap-1.5">
                  <Zap className="w-4 h-4 text-indigo-600" />
                  2. Waste-to-Energy (WtE) Combustion Model
                </h4>
                <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200 font-mono text-[11px] text-slate-800">
                  Power (MW) = (Waste_TPD × Combustible_Fraction × NCV × Efficiency) / (24 hr × 860 kcal/kWh)
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div className="p-2 rounded bg-slate-50 border border-slate-100">
                    <span className="font-semibold block text-slate-800">Combustible Fraction:</span>
                    <span>20.0% (Derived from CPCB 59-city recyclables & dry combustibles)</span>
                  </div>
                  <div className="p-2 rounded bg-slate-50 border border-slate-100">
                    <span className="font-semibold block text-slate-800">Net Calorific Value:</span>
                    <span>1,100 kcal/kg (Standard baseline for mixed Indian municipal waste)</span>
                  </div>
                  <div className="p-2 rounded bg-slate-50 border border-slate-100">
                    <span className="font-semibold block text-slate-800">Conversion Efficiency:</span>
                    <span>22.0% gross thermodynamic electrical efficiency</span>
                  </div>
                  <div className="p-2 rounded bg-slate-50 border border-slate-100">
                    <span className="font-semibold block text-slate-800">Effective Multiplier:</span>
                    <span>~0.002345 MW per TPD (~2.35 MW per 1,000 TPD of MSW)</span>
                  </div>
                </div>
                <p className="text-[11px] text-slate-500 italic">
                  Note: Computed only at State level where verified solid waste generation tonnages exist. PIN-code potential is withheld due to absence of local generation and calorific testing.
                </p>
              </div>

              {/* Composition Baseline */}
              <div className="p-4 rounded-xl border border-slate-200 bg-white space-y-2">
                <h4 className="font-bold text-slate-900 text-xs flex items-center gap-1.5">
                  <PieChart className="w-4 h-4 text-teal-600" />
                  3. CPCB / NEERI 59-City Waste Characterization Baseline
                </h4>
                <p className="text-[11px] text-slate-600">
                  Conducted by NEERI across 35 metro cities and 24 state capitals:
                </p>
                <div className="grid grid-cols-3 gap-2 text-[11px]">
                  <div className="p-2 rounded bg-teal-50/60 border border-teal-100 text-teal-900">
                    <span className="font-bold block">40% - 60%</span>
                    <span>Compostable Organic</span>
                  </div>
                  <div className="p-2 rounded bg-teal-50/60 border border-teal-100 text-teal-900">
                    <span className="font-bold block">10% - 25%</span>
                    <span>Recyclable Matter</span>
                  </div>
                  <div className="p-2 rounded bg-teal-50/60 border border-teal-100 text-teal-900">
                    <span className="font-bold block">30% - 60%</span>
                    <span>Moisture Content</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: Integrity & Limitations */}
          {activeTab === 'integrity' && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl border border-amber-200 bg-amber-50/70 space-y-2 text-amber-950">
                <h4 className="font-bold text-xs flex items-center gap-1.5 text-amber-900">
                  <ShieldAlert className="w-4 h-4 text-amber-700" />
                  Strict Data Integrity Standards
                </h4>
                {methodologyData?.data_integrity_principles ? (
                  <ul className="list-disc list-inside space-y-1.5 text-[11px] leading-relaxed">
                    {methodologyData.data_integrity_principles.map((principle: string, idx: number) => (
                      <li key={idx}>{principle}</li>
                    ))}
                  </ul>
                ) : (
                  <ul className="list-disc list-inside space-y-1.5 text-[11px] leading-relaxed">
                    <li>
                      <strong>No False Granularity:</strong> CPCB publishes official solid waste data at State/UT and city levels, NOT at postal PIN-code level. State-level totals are never presented as PIN-code measurements.
                    </li>
                    <li>
                      <strong>No Uniform Disaggregation:</strong> Dividing state totals uniformly among postal codes would produce completely fictional local figures and is strictly avoided.
                    </li>
                    <li>
                      <strong>Explicit Availability Status:</strong> When viewing a PIN-code polygon, the UI explicitly flags direct postal measurements as "Data Unavailable" while providing parent state context for reference.
                    </li>
                  </ul>
                )}
              </div>

              <div className="p-4 rounded-xl border border-slate-200 bg-white space-y-2">
                <h4 className="font-bold text-xs text-slate-900 flex items-center gap-1.5">
                  <Layers className="w-4 h-4 text-slate-600" />
                  Geospatial & Boundary Limitations
                </h4>
                <ul className="list-disc list-inside space-y-1.5 text-[11px] text-slate-600 leading-relaxed">
                  <li>
                    <strong>Postal vs Municipal Boundaries:</strong> PIN-code polygons represent postal delivery catchments established by India Post rather than statutory Urban Local Body (ULB) wards or census blocks.
                  </li>
                  <li>
                    <strong>Reporting Period Alignment:</strong> Solid waste data reflects 2020-21, Plastic waste spans 2018-2023, and Waste Composition is derived from the CPCB 59-city baseline.
                  </li>
                  <li>
                    <strong>Boundary Simplification:</strong> State polygons are dissolved from postal polygons and topology-preserved to ensure high performance and smooth 60fps rendering in modern web browsers.
                  </li>
                </ul>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-slate-200 bg-slate-50 flex items-center justify-between">
          <span className="text-[11px] text-slate-500">
            Source: Central Pollution Control Board (CPCB) & Data.gov.in
          </span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold transition-colors"
          >
            Close Documentation
          </button>
        </div>
      </div>
    </div>
  );
};

export default InfoModal;
