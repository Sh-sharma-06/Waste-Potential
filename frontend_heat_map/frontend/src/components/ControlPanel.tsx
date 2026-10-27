import React from 'react';
import {
  Trash2,
  AlertTriangle,
  Zap,
  PieChart,
  Map,
  Info,
  Calendar,
} from 'lucide-react';
import type { HeatmapMode, GranularityView } from '../types';

interface ControlPanelProps {
  mode: HeatmapMode;
  onModeChange: (mode: HeatmapMode) => void;
  view: GranularityView;
  onViewChange: (view: GranularityView) => void;
  metricType: 'solid' | 'plastic';
  onMetricTypeChange: (type: 'solid' | 'plastic') => void;
  plasticYear: string;
  onPlasticYearChange: (year: string) => void;
  plasticYears: string[];
}

export const ControlPanel: React.FC<ControlPanelProps> = ({
  mode,
  onModeChange,
  view,
  onViewChange,
  metricType,
  onMetricTypeChange,
  plasticYear,
  onPlasticYearChange,
  plasticYears,
}) => {
  const modesList = [
    {
      id: 'waste_generation' as HeatmapMode,
      label: 'Waste Generation',
      subtitle: metricType === 'solid' ? 'Solid Waste (TPD)' : `Plastic Waste (${plasticYear})`,
      icon: Trash2,
      color: 'emerald',
    },
    {
      id: 'processing_gap' as HeatmapMode,
      label: 'Processing Gap',
      subtitle: 'Unprocessed Waste (TPD / %)',
      icon: AlertTriangle,
      color: 'amber',
    },
    {
      id: 'waste_to_energy' as HeatmapMode,
      label: 'WtE Potential',
      subtitle: 'Power Potential (MW)',
      icon: Zap,
      color: 'blue',
    },
    {
      id: 'waste_composition' as HeatmapMode,
      label: 'Waste Composition',
      subtitle: 'CPCB 59-City Baseline',
      icon: PieChart,
      color: 'teal',
    },
  ];

  return (
    <div className="bg-white/95 backdrop-blur-md rounded-2xl border border-slate-200/90 shadow-sm p-4 space-y-4">
      {/* 1. Mode Selector */}
      <div>
        <label className="text-xs font-bold text-slate-700 uppercase tracking-wider block mb-2">
          Heatmap Mode
        </label>
        <div className="grid grid-cols-2 gap-2">
          {modesList.map((m) => {
            const Icon = m.icon;
            const isActive = mode === m.id;
            return (
              <button
                key={m.id}
                onClick={() => onModeChange(m.id)}
                className={`flex items-start gap-2.5 p-2.5 rounded-xl border text-left transition-all relative ${
                  isActive
                    ? 'border-emerald-600 bg-emerald-50/70 shadow-xs ring-1 ring-emerald-600/30'
                    : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50/80 bg-white'
                }`}
              >
                <div
                  className={`p-1.5 rounded-lg shrink-0 mt-0.5 ${
                    isActive
                      ? 'bg-emerald-600 text-white'
                      : 'bg-slate-100 text-slate-600'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                </div>
                <div className="min-w-0">
                  <div
                    className={`text-xs font-semibold leading-tight truncate ${
                      isActive ? 'text-emerald-950 font-bold' : 'text-slate-800'
                    }`}
                  >
                    {m.label}
                  </div>
                  <div className="text-[10px] text-slate-500 leading-tight truncate mt-0.5">
                    {m.subtitle}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Mode-Specific Sub-Options for Waste Generation */}
      {mode === 'waste_generation' && (
        <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-200/80 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-slate-700">Metric Type:</span>
            <div className="flex bg-slate-200/80 p-0.5 rounded-lg text-xs">
              <button
                onClick={() => onMetricTypeChange('solid')}
                className={`px-2.5 py-1 rounded-md font-medium text-[11px] transition-all ${
                  metricType === 'solid'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Solid Waste (TPD)
              </button>
              <button
                onClick={() => onMetricTypeChange('plastic')}
                className={`px-2.5 py-1 rounded-md font-medium text-[11px] transition-all ${
                  metricType === 'plastic'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Plastic Waste (TPY)
              </button>
            </div>
          </div>

          {metricType === 'plastic' && (
            <div className="flex items-center justify-between pt-1">
              <span className="text-[11px] font-medium text-slate-600 flex items-center gap-1">
                <Calendar className="w-3 h-3 text-slate-400" /> Reporting Year:
              </span>
              <select
                value={plasticYear}
                onChange={(e) => onPlasticYearChange(e.target.value)}
                className="text-xs bg-white border border-slate-200 rounded-md px-2 py-1 text-slate-700 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                {plasticYears.map((yr) => (
                  <option key={yr} value={yr}>
                    {yr}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      )}

      {/* 2. Granularity / View Toggle */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
            <Map className="w-3.5 h-3.5 text-slate-400" /> Map View
          </label>
        </div>
        <div className="grid grid-cols-2 gap-1.5 bg-slate-100 p-1 rounded-xl">
          <button
            onClick={() => onViewChange('state')}
            className={`py-1.5 px-2 rounded-lg text-xs font-semibold transition-all ${
              view === 'state'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            State Overview
          </button>
          <button
            onClick={() => onViewChange('pincode')}
            className={`py-1.5 px-2 rounded-lg text-xs font-semibold transition-all ${
              view === 'pincode'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            PIN-Code Polygons
          </button>
        </div>
      </div>

      {/* 3. Dynamic Color Legend */}
      <div className="pt-2 border-t border-slate-100">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
            Color Legend
          </span>
          <span className="text-[11px] font-medium text-slate-500">
            {mode === 'waste_generation'
              ? metricType === 'solid'
                ? 'TPD'
                : 'TPY'
              : mode === 'processing_gap'
              ? 'TPD Unprocessed'
              : mode === 'waste_to_energy'
              ? 'MW Capacity'
              : '% Compostable'}
          </span>
        </div>

        {/* Dynamic Scale Bars */}
        {mode === 'waste_generation' && (
          <div className="space-y-1.5">
            <div className="h-3 rounded-full bg-gradient-to-r from-emerald-200 via-amber-300 via-orange-400 to-rose-600 shadow-inner" />
            <div className="flex justify-between text-[10px] text-slate-500 font-medium">
              <span>{metricType === 'solid' ? '< 500' : '< 5k'}</span>
              <span>{metricType === 'solid' ? '2,000' : '50k'}</span>
              <span>{metricType === 'solid' ? '8,000' : '200k'}</span>
              <span>{metricType === 'solid' ? '22,000+' : '500k+'}</span>
            </div>
          </div>
        )}

        {mode === 'processing_gap' && (
          <div className="space-y-1.5">
            <div className="h-3 rounded-full bg-gradient-to-r from-emerald-300 via-amber-300 via-orange-400 to-purple-700 shadow-inner" />
            <div className="flex justify-between text-[10px] text-slate-500 font-medium">
              <span>0 (100% Treated)</span>
              <span>1,000 TPD</span>
              <span>5,000 TPD</span>
              <span>13,000+ TPD</span>
            </div>
          </div>
        )}

        {mode === 'waste_to_energy' && (
          <div className="space-y-1.5">
            <div className="h-3 rounded-full bg-gradient-to-r from-cyan-200 via-blue-400 to-indigo-700 shadow-inner" />
            <div className="flex justify-between text-[10px] text-slate-500 font-medium">
              <span>0.1 MW</span>
              <span>10 MW</span>
              <span>25 MW</span>
              <span>50+ MW</span>
            </div>
          </div>
        )}

        {mode === 'waste_composition' && (
          <div className="space-y-1.5">
            <div className="h-3 rounded-full bg-gradient-to-r from-teal-200 to-teal-700 shadow-inner" />
            <div className="flex justify-between text-[10px] text-slate-500 font-medium">
              <span>40% Compostable</span>
              <span>50%</span>
              <span>60% Compostable</span>
            </div>
          </div>
        )}

        {/* Legend Status Badges */}
        <div className="flex flex-wrap items-center gap-3 pt-2 text-[11px] text-slate-600">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
            <span>Reported Value</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-indigo-500" />
            <span>Engineered Estimate</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-300 border border-slate-400 border-dashed" />
            <span>Data Unavailable / NA</span>
          </div>
        </div>
      </div>

      {/* Informative Mode Callout */}
      <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-200/80 flex items-start gap-2 text-[11px] text-slate-600">
        <Info className="w-3.5 h-3.5 text-emerald-600 shrink-0 mt-0.5" />
        <div>
          {mode === 'waste_composition' && (
            <span>
              <strong>CPCB 59-City Baseline:</strong> Shows verified physical composition from CPCB/NEERI metro study. State & PIN-code specific composition splits are not collected by CPCB.
            </span>
          )}
          {mode === 'waste_to_energy' && (
            <span>
              <strong>MNRE Conversion Model:</strong> Power potential is calculated at State level using 20% combustible fraction and 1,100 kcal/kg NCV. PIN-code potential is omitted due to missing local inputs.
            </span>
          )}
          {mode === 'processing_gap' && (
            <span>
              <strong>Processing Gap:</strong> Computed as (Solid Waste Generated - Treated). Territories with 'NA' treated figures are marked as Data Unavailable.
            </span>
          )}
          {mode === 'waste_generation' && (
            <span>
              <strong>Verified Figures:</strong> Solid waste data reflects CPCB 2020-21 state totals. Never uniformly divided across PIN codes to maintain data integrity.
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

export default ControlPanel;
