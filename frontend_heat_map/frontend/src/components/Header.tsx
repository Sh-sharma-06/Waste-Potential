import React from 'react';
import { Layers, BookOpen, ShieldCheck } from 'lucide-react';
import SearchBar from './SearchBar';
import type { SearchResult } from '../types';

interface HeaderProps {
  onSelectResult: (result: SearchResult) => void;
  onClearSearch?: () => void;
  onOpenInfo: () => void;
  backendHealthy: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  onSelectResult,
  onClearSearch,
  onOpenInfo,
  backendHealthy,
}) => {
  return (
    <header className="bg-white/95 backdrop-blur-md border-b border-slate-200/80 sticky top-0 z-30 px-4 py-2.5 shadow-sm">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-3">
        {/* Brand & Badges */}
        <div className="flex items-center gap-3 w-full md:w-auto justify-between md:justify-start">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-500 flex items-center justify-center text-white shadow-md shadow-emerald-600/20">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-base font-bold tracking-tight text-slate-900 flex items-center gap-2">
                India Waste Heatmap
                <span className="hidden sm:inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                  <ShieldCheck className="w-3 h-3" /> CPCB Verified
                </span>
              </h1>
              <p className="text-[11px] text-slate-500 leading-tight">
                Solid Waste • Processing Gap • Waste-to-Energy • Plastic Trends
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 md:hidden">
            <button
              onClick={onOpenInfo}
              className="p-1.5 text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
              title="Methodology & Sources"
            >
              <BookOpen className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Global Search Bar */}
        <div className="w-full md:w-96">
          <SearchBar onSelectResult={onSelectResult} onClear={onClearSearch} />
        </div>

        {/* Action Controls & Health */}
        <div className="hidden md:flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 text-xs font-medium">
            <span
              className={`w-2 h-2 rounded-full ${
                backendHealthy ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'
              }`}
            />
            <span className="text-[11px]">
              {backendHealthy ? 'API Connected' : 'Connecting API...'}
            </span>
          </div>

          <button
            onClick={onOpenInfo}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200/90 border border-slate-200/70 transition-colors shadow-xs"
          >
            <BookOpen className="w-3.5 h-3.5 text-emerald-600" />
            <span>Sources & Methodology</span>
          </button>
        </div>
      </div>
    </header>
  );
};

export default Header;
