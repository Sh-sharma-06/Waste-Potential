import React, { useState } from 'react';
import {
  MapPin,
  Building,
  Compass,
  ArrowRight,
  Loader2,
  AlertCircle,
  X,
  Layers,
  Sparkles,
} from 'lucide-react';
import { searchLocations } from '../services/api';
import type { SearchResult } from '../types';

interface SearchPanelProps {
  onSelectResult: (result: SearchResult) => void;
  onClearSearch?: () => void;
}

export const SearchPanel: React.FC<SearchPanelProps> = ({
  onSelectResult,
  onClearSearch,
}) => {
  // Individual field inputs
  const [pinInput, setPinInput] = useState('');
  const [cityInput, setCityInput] = useState('');
  const [districtInput, setDistrictInput] = useState('');

  // Loading states for each independent Apply action
  const [loadingType, setLoadingType] = useState<'pincode' | 'city' | 'district' | null>(null);

  // Error / Feedback messages
  const [errorMsg, setErrorMsg] = useState<{ type: string; message: string } | null>(null);

  // Disambiguation results (when duplicate names or multiple matches exist)
  const [multiResults, setMultiResults] = useState<{
    type: string;
    query: string;
    items: SearchResult[];
  } | null>(null);

  // 1. PIN Code Search Trigger
  const handlePinSearch = async () => {
    const trimmed = pinInput.trim();
    setErrorMsg(null);
    setMultiResults(null);

    if (!trimmed) {
      setErrorMsg({ type: 'pincode', message: 'Please enter a 6-digit PIN code.' });
      return;
    }

    if (!/^\d{6}$/.test(trimmed)) {
      if (!/^\d+$/.test(trimmed)) {
        setErrorMsg({ type: 'pincode', message: 'PIN code must contain numbers only.' });
      } else {
        setErrorMsg({
          type: 'pincode',
          message: `PIN code must be exactly 6 digits (you entered ${trimmed.length} digits).`,
        });
      }
      return;
    }

    setLoadingType('pincode');
    try {
      const resp = await searchLocations(trimmed, 'pincode');
      if (resp.error) {
        setErrorMsg({ type: 'pincode', message: resp.error });
      } else if (resp.results.length === 0) {
        setErrorMsg({
          type: 'pincode',
          message: `PIN code ${trimmed} was not found in the India Post database.`,
        });
      } else if (resp.results.length === 1) {
        onSelectResult(resp.results[0]);
      } else {
        // Disambiguate if multiple post offices under same PIN
        setMultiResults({ type: 'pincode', query: trimmed, items: resp.results });
      }
    } catch (err: any) {
      setErrorMsg({ type: 'pincode', message: 'Network error searching PIN code.' });
    } finally {
      setLoadingType(null);
    }
  };

  // 2. City Search Trigger
  const handleCitySearch = async () => {
    const trimmed = cityInput.trim();
    setErrorMsg(null);
    setMultiResults(null);

    if (!trimmed || trimmed.length < 2) {
      setErrorMsg({ type: 'city', message: 'Please enter at least 2 characters for city.' });
      return;
    }

    setLoadingType('city');
    try {
      const resp = await searchLocations(trimmed, 'city');
      if (resp.error) {
        setErrorMsg({ type: 'city', message: resp.error });
      } else if (resp.results.length === 0) {
        setErrorMsg({
          type: 'city',
          message: `No matching city found for "${trimmed}".`,
        });
      } else if (resp.results.length === 1) {
        onSelectResult(resp.results[0]);
      } else {
        // Show disambiguation selection (e.g. Rampur, Bilaspur, Aurangabad)
        setMultiResults({ type: 'city', query: trimmed, items: resp.results });
      }
    } catch (err: any) {
      setErrorMsg({ type: 'city', message: 'Network error searching city.' });
    } finally {
      setLoadingType(null);
    }
  };

  // 3. District Search Trigger
  const handleDistrictSearch = async () => {
    const trimmed = districtInput.trim();
    setErrorMsg(null);
    setMultiResults(null);

    if (!trimmed || trimmed.length < 2) {
      setErrorMsg({ type: 'district', message: 'Please enter at least 2 characters for district.' });
      return;
    }

    setLoadingType('district');
    try {
      const resp = await searchLocations(trimmed, 'district');
      if (resp.error) {
        setErrorMsg({ type: 'district', message: resp.error });
      } else if (resp.results.length === 0) {
        setErrorMsg({
          type: 'district',
          message: `No matching district found for "${trimmed}".`,
        });
      } else if (resp.results.length === 1) {
        onSelectResult(resp.results[0]);
      } else {
        // Show disambiguation list (e.g. Bilaspur in Chhattisgarh vs Bilaspur in HP)
        setMultiResults({ type: 'district', query: trimmed, items: resp.results });
      }
    } catch (err: any) {
      setErrorMsg({ type: 'district', message: 'Network error searching district.' });
    } finally {
      setLoadingType(null);
    }
  };

  const handleSelectDisambiguated = (item: SearchResult) => {
    onSelectResult(item);
    setMultiResults(null);
  };

  const hasAnyInput = Boolean(pinInput || cityInput || districtInput);

  const handleClearAll = () => {
    setPinInput('');
    setCityInput('');
    setDistrictInput('');
    setErrorMsg(null);
    setMultiResults(null);
    if (onClearSearch) {
      onClearSearch();
    }
  };

  return (
    <div className="bg-white/95 backdrop-blur-md rounded-2xl border border-slate-200/90 shadow-sm p-4 space-y-3.5">
      <div className="flex items-center justify-between border-b border-slate-100 pb-2">
        <div className="flex items-center gap-1.5 text-xs font-bold text-slate-800 uppercase tracking-wider">
          <Layers className="w-3.5 h-3.5 text-emerald-600" />
          <span>Regional Location Search</span>
        </div>
        <div className="flex items-center gap-2">
          {hasAnyInput && (
            <button
              onClick={handleClearAll}
              className="text-[10px] text-slate-500 hover:text-slate-800 underline font-medium"
              title="Clear search inputs and return to full-India map"
            >
              Clear
            </button>
          )}
          <span className="text-[10px] text-slate-400 font-medium">Independent Apply</span>
        </div>
      </div>

      {/* --- FIELD 1: PIN CODE SEARCH --- */}
      <div className="space-y-1">
        <label className="text-[11px] font-bold text-slate-700 flex items-center justify-between">
          <span className="flex items-center gap-1.5">
            <MapPin className="w-3.5 h-3.5 text-amber-600" />
            <span>PIN Code</span>
          </span>
          <span className="text-[10px] font-normal text-slate-400">6 digits</span>
        </label>
        <div className="flex gap-1.5">
          <input
            type="text"
            maxLength={6}
            value={pinInput}
            onChange={(e) => {
              setPinInput(e.target.value);
              if (errorMsg?.type === 'pincode') setErrorMsg(null);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                handlePinSearch();
              }
            }}
            placeholder="e.g. 110001, 400001"
            className="flex-1 px-3 py-1.5 text-xs bg-slate-50 focus:bg-white border border-slate-200 focus:border-amber-500 rounded-lg text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-amber-500/30 transition-all font-mono"
          />
          <button
            onClick={handlePinSearch}
            disabled={loadingType === 'pincode'}
            className="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 active:bg-amber-800 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors flex items-center gap-1 shrink-0 disabled:opacity-50"
          >
            {loadingType === 'pincode' ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <span>Apply</span>
            )}
          </button>
        </div>
        {errorMsg?.type === 'pincode' && (
          <div className="text-[11px] text-rose-600 flex items-center gap-1 pt-0.5">
            <AlertCircle className="w-3 h-3 shrink-0" />
            <span>{errorMsg.message}</span>
          </div>
        )}
      </div>

      {/* --- FIELD 2: CITY SEARCH --- */}
      <div className="space-y-1">
        <label className="text-[11px] font-bold text-slate-700 flex items-center justify-between">
          <span className="flex items-center gap-1.5">
            <Building className="w-3.5 h-3.5 text-teal-600" />
            <span>City / Urban Area</span>
          </span>
          <span className="text-[10px] font-normal text-slate-400">CPCB 59-City & towns</span>
        </label>
        <div className="flex gap-1.5">
          <input
            type="text"
            value={cityInput}
            onChange={(e) => {
              setCityInput(e.target.value);
              if (errorMsg?.type === 'city') setErrorMsg(null);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                handleCitySearch();
              }
            }}
            placeholder="e.g. Nagpur, Pune, Kolkata"
            className="flex-1 px-3 py-1.5 text-xs bg-slate-50 focus:bg-white border border-slate-200 focus:border-teal-500 rounded-lg text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-teal-500/30 transition-all"
          />
          <button
            onClick={handleCitySearch}
            disabled={loadingType === 'city'}
            className="px-3 py-1.5 bg-teal-600 hover:bg-teal-700 active:bg-teal-800 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors flex items-center gap-1 shrink-0 disabled:opacity-50"
          >
            {loadingType === 'city' ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <span>Apply</span>
            )}
          </button>
        </div>
        {errorMsg?.type === 'city' && (
          <div className="text-[11px] text-rose-600 flex items-center gap-1 pt-0.5">
            <AlertCircle className="w-3 h-3 shrink-0" />
            <span>{errorMsg.message}</span>
          </div>
        )}
      </div>

      {/* --- FIELD 3: DISTRICT SEARCH --- */}
      <div className="space-y-1">
        <label className="text-[11px] font-bold text-slate-700 flex items-center justify-between">
          <span className="flex items-center gap-1.5">
            <Compass className="w-3.5 h-3.5 text-indigo-600" />
            <span>District</span>
          </span>
          <span className="text-[10px] font-normal text-slate-400">750 districts</span>
        </label>
        <div className="flex gap-1.5">
          <input
            type="text"
            value={districtInput}
            onChange={(e) => {
              setDistrictInput(e.target.value);
              if (errorMsg?.type === 'district') setErrorMsg(null);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                handleDistrictSearch();
              }
            }}
            placeholder="e.g. Bilaspur, Thane, Jaipur"
            className="flex-1 px-3 py-1.5 text-xs bg-slate-50 focus:bg-white border border-slate-200 focus:border-indigo-500 rounded-lg text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-indigo-500/30 transition-all"
          />
          <button
            onClick={handleDistrictSearch}
            disabled={loadingType === 'district'}
            className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors flex items-center gap-1 shrink-0 disabled:opacity-50"
          >
            {loadingType === 'district' ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <span>Apply</span>
            )}
          </button>
        </div>
        {errorMsg?.type === 'district' && (
          <div className="text-[11px] text-rose-600 flex items-center gap-1 pt-0.5">
            <AlertCircle className="w-3 h-3 shrink-0" />
            <span>{errorMsg.message}</span>
          </div>
        )}
      </div>

      {/* --- DISAMBIGUATION MODAL / CARD LIST (DUPLICATE LOCATIONS) --- */}
      {multiResults && (
        <div className="mt-2 p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
          <div className="flex items-center justify-between">
            <div className="text-[11px] font-bold text-slate-800 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-emerald-600" />
              <span>Multiple matches found for "{multiResults.query}"</span>
            </div>
            <button
              onClick={() => setMultiResults(null)}
              className="p-1 text-slate-400 hover:text-slate-600 rounded"
              title="Close list"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <p className="text-[10px] text-slate-500">
            Select the specific {multiResults.type} below to inspect its waste profile:
          </p>
          <div className="max-h-48 overflow-y-auto space-y-1.5 divide-y divide-slate-100">
            {multiResults.items.map((item, idx) => (
              <button
                key={`${item.id}-${idx}`}
                onClick={() => handleSelectDisambiguated(item)}
                className="w-full text-left p-2 rounded-lg bg-white hover:bg-emerald-50 border border-slate-200/80 hover:border-emerald-300 transition-colors flex items-start justify-between gap-2 group"
              >
                <div>
                  <div className="text-xs font-bold text-slate-900 group-hover:text-emerald-800 flex items-center gap-1.5">
                    <span>{item.title}</span>
                    {item.is_cpcb_studied && (
                      <span className="text-[9px] font-semibold px-1.5 py-0.2 rounded bg-teal-100 text-teal-800">
                        CPCB Studied
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-slate-500 mt-0.5">
                    {item.subtitle}
                  </div>
                </div>
                <ArrowRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-emerald-600 shrink-0 mt-1" />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default SearchPanel;
