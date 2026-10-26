import React, { useState, useEffect, useRef } from 'react';
import { Search, MapPin, X, Loader2, Building, Globe } from 'lucide-react';
import { searchRegions } from '../services/api';
import type { SearchResult } from '../types';

interface SearchBarProps {
  onSelectResult: (result: SearchResult) => void;
  onClear?: () => void;
}

export const SearchBar: React.FC<SearchBarProps> = ({ onSelectResult, onClear }) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!query || query.trim().length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await searchRegions(query.trim());
        setResults(res);
        setIsOpen(true);
      } catch (err) {
        console.error('Search error:', err);
      } finally {
        setLoading(false);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [query]);

  // Click outside listener
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelect = (item: SearchResult) => {
    onSelectResult(item);
    setQuery(item.title);
    setIsOpen(false);
  };

  const handleClear = () => {
    setQuery('');
    setResults([]);
    setIsOpen(false);
    if (onClear) {
      onClear();
    }
  };

  return (
    <div ref={containerRef} className="relative w-full">
      <div className="relative flex items-center">
        <Search className="w-4 h-4 text-slate-400 absolute left-3 pointer-events-none" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => {
            if (results.length > 0) setIsOpen(true);
          }}
          placeholder="Search PIN code, Post Office, District, State..."
          className="w-full pl-9 pr-8 py-1.5 text-xs bg-slate-100 hover:bg-slate-100/80 focus:bg-white border border-slate-200 focus:border-emerald-500 rounded-lg text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 transition-all"
        />
        {loading && (
          <Loader2 className="w-3.5 h-3.5 text-slate-400 animate-spin absolute right-2.5" />
        )}
        {!loading && query && (
          <button
            onClick={handleClear}
            className="p-1 text-slate-400 hover:text-slate-600 absolute right-2 rounded-full"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* Autocomplete Dropdown */}
      {isOpen && results.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-1.5 bg-white border border-slate-200 rounded-xl shadow-xl z-50 max-h-72 overflow-y-auto divide-y divide-slate-100">
          {results.map((item, idx) => (
            <button
              key={`${item.type}-${item.id}-${idx}`}
              onClick={() => handleSelect(item)}
              className="w-full text-left px-3.5 py-2.5 hover:bg-emerald-50/60 flex items-start gap-2.5 transition-colors group"
            >
              <div className="p-1.5 rounded-lg bg-slate-100 group-hover:bg-emerald-100 text-slate-600 group-hover:text-emerald-700 mt-0.5 transition-colors">
                {item.type === 'pincode' && <MapPin className="w-3.5 h-3.5" />}
                {item.type === 'city' && <Building className="w-3.5 h-3.5" />}
                {item.type === 'district' && <Building className="w-3.5 h-3.5" />}
                {item.type === 'state' && <Globe className="w-3.5 h-3.5" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-semibold text-slate-900 truncate flex items-center gap-1.5">
                  <span>{item.title}</span>
                  {item.is_cpcb_studied && (
                    <span className="text-[9px] px-1 rounded bg-teal-100 text-teal-800 font-semibold">
                      CPCB
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-slate-500 truncate">
                  {item.subtitle}
                </div>
              </div>
              <span className="text-[10px] font-medium px-2 py-0.5 rounded uppercase tracking-wider bg-slate-100 text-slate-600">
                {item.type}
              </span>
            </button>
          ))}
        </div>
      )}

      {isOpen && !loading && query.trim().length >= 2 && results.length === 0 && (
        <div className="absolute top-full left-0 right-0 mt-1.5 bg-white border border-slate-200 rounded-xl shadow-xl z-50 p-4 text-center text-xs text-slate-500">
          No matching postal code, district, or state found for "{query}".
        </div>
      )}
    </div>
  );
};

export default SearchBar;
