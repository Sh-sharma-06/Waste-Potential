import React, { useState, useEffect, useCallback, useRef } from 'react';
import Header from './components/Header';
import SearchPanel from './components/SearchPanel';
import ControlPanel from './components/ControlPanel';
import MapComponent from './components/MapComponent';
import DetailsPanel from './components/DetailsPanel';
import InfoModal from './components/InfoModal';
import type {
  HeatmapMode,
  GranularityView,
  FilterOptions,
  RegionDetails,
  SearchResult,
} from './types';
import {
  fetchHealth,
  fetchFilters,
  fetchHeatmapData,
  fetchRegionDetails,
  fetchSources,
  fetchMethodology,
} from './services/api';
import { AlertCircle, RefreshCw } from 'lucide-react';

export const App: React.FC = () => {
  // Navigation & Control States
  const [mode, setMode] = useState<HeatmapMode>('waste_generation');
  const [view, setView] = useState<GranularityView>('state');
  const [selectedState, setSelectedState] = useState<string>('');
  const [selectedDistrict, setSelectedDistrict] = useState<string>('');
  const [metricType, setMetricType] = useState<'solid' | 'plastic'>('solid');
  const [plasticYear, setPlasticYear] = useState<string>('2022-23');

  // Data States
  const [geoJsonData, setGeoJsonData] = useState<any>(null);
  const [selectedIdentifier, setSelectedIdentifier] = useState<string>('state:maharashtra');
  const [regionDetails, setRegionDetails] = useState<RegionDetails | null>(null);
  const [filtersData, setFiltersData] = useState<FilterOptions | null>(null);
  const [sourcesData, setSourcesData] = useState<any>(null);
  const [methodologyData, setMethodologyData] = useState<any>(null);
  const [targetCoords, setTargetCoords] = useState<{ lat: number; lon: number; zoom?: number } | null>(null);

  // UI States
  const [isMapLoading, setIsMapLoading] = useState<boolean>(true);
  const [isDetailsLoading, setIsDetailsLoading] = useState<boolean>(false);
  const [isInfoModalOpen, setIsInfoModalOpen] = useState<boolean>(false);
  const [backendHealthy, setBackendHealthy] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Initial Load: Health, Filters, Metadata & Default Details
  useEffect(() => {
    async function initApp() {
      try {
        const [healthRes, filtersRes, sourcesRes, methodRes] = await Promise.all([
          fetchHealth().catch(() => ({ status: 'error' })),
          fetchFilters(),
          fetchSources().catch(() => null),
          fetchMethodology().catch(() => null),
        ]);

        setBackendHealthy(healthRes.status === 'healthy');
        setFiltersData(filtersRes);
        setSourcesData(sourcesRes);
        setMethodologyData(methodRes);

        // Load initial default region details (Maharashtra)
        const initialDetails = await fetchRegionDetails('state:maharashtra');
        setRegionDetails(initialDetails);

        // Phase 3: Read pincode from URL params on initial load
        const urlParams = new URLSearchParams(window.location.search);
        const initialPin = urlParams.get('pincode');
        if (initialPin && /^\d{6}$/.test(initialPin.trim())) {
          handlePincodeNavigation(initialPin.trim());
        }
      } catch (err: any) {
        console.error('Initialization error:', err);
        setErrorMessage('Failed to connect to backend API. Please ensure the server is running on port 8001.');
        setBackendHealthy(false);
      }
    }
    initApp();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fetch Heatmap GeoJSON when filters/mode change
  const loadHeatmap = useCallback(async () => {
    setIsMapLoading(true);
    setErrorMessage(null);
    try {
      const data = await fetchHeatmapData({
        mode,
        view,
        state: selectedState,
        district: selectedDistrict,
        metricType,
        plasticYear,
      });
      setGeoJsonData(data);
    } catch (err: any) {
      console.error('Heatmap load error:', err);
      setErrorMessage(err.message || 'Error loading map geometry.');
    } finally {
      setIsMapLoading(false);
    }
  }, [mode, view, selectedState, selectedDistrict, metricType, plasticYear]);

  useEffect(() => {
    loadHeatmap();
  }, [loadHeatmap]);

  // Load Region Details on Selection
  const handleSelectRegion = useCallback(async (identifier: string) => {
    setSelectedIdentifier(identifier);
    setIsDetailsLoading(true);
    try {
      const details = await fetchRegionDetails(identifier);
      setRegionDetails(details);
    } catch (err) {
      console.error('Details load error:', err);
    } finally {
      setIsDetailsLoading(false);
    }
  }, []);

  // Handle Search Result Selection (All Levels: PIN, City, District, State)
  const handleSelectSearchResult = useCallback((result: SearchResult) => {
    const targetId = result.id || (result.pincode ? `pincode:${result.pincode}` : result.state);
    const isKarnataka = result.state?.toUpperCase() === 'KARNATAKA' || result.title?.toUpperCase().includes('KARNATAKA');

    if (result.type === 'pincode' && result.pincode) {
      setSelectedIdentifier(targetId);
      handleSelectRegion(targetId);

      if (isKarnataka) {
        // Switch to Karnataka-focused heatmap with PIN-code polygons coloured by district stats
        setSelectedState('Karnataka');
        setSelectedDistrict('');
        setView('pincode');
      } else {
        // Outside Karnataka: Preserve national choropleth map view
        setSelectedState('');
        setSelectedDistrict('');
        setView('state');
      }

      if (result.lat && result.lon) {
        setTargetCoords({ lat: result.lat, lon: result.lon, zoom: 11 });
      }
    } else if (result.type === 'city') {
      setSelectedIdentifier(targetId);
      handleSelectRegion(targetId);

      if (isKarnataka) {
        setSelectedState('Karnataka');
        setSelectedDistrict(result.district || '');
        setView('pincode');
      } else {
        setSelectedState('');
        setSelectedDistrict('');
        setView('state');
      }

      if (result.lat && result.lon) {
        setTargetCoords({ lat: result.lat, lon: result.lon, zoom: 10 });
      }
    } else if (result.type === 'district' && result.district) {
      setSelectedIdentifier(targetId);
      handleSelectRegion(targetId);

      if (isKarnataka) {
        setSelectedState('Karnataka');
        setSelectedDistrict(result.district);
        setView('pincode');
      } else {
        setSelectedState('');
        setSelectedDistrict('');
        setView('state');
      }

      if (result.lat && result.lon) {
        setTargetCoords({ lat: result.lat, lon: result.lon, zoom: 9 });
      }
    } else if (result.type === 'state') {
      const st = result.state || result.title;
      setSelectedIdentifier(targetId);
      handleSelectRegion(targetId);

      if (st.toUpperCase() === 'KARNATAKA') {
        // User searched for Karnataka: Display Karnataka-focused heatmap with PIN-code polygons
        setSelectedState('Karnataka');
        setSelectedDistrict('');
        setView('pincode');
        setTargetCoords({ lat: 15.3173, lon: 75.7139, zoom: 7 });
      } else {
        // Other Indian states: full-India choropleth heatmap
        setSelectedState(st);
        setSelectedDistrict('');
        setView('state');
        setTargetCoords({ lat: 22.9734, lon: 78.6569, zoom: 5 });
      }
    }
  }, [handleSelectRegion]);

  // Phase 3: Handle pincode navigation (shared by postMessage + URL params)
  const handlePincodeNavigation = useCallback(async (pincode: string) => {
    if (!/^\d{6}$/.test(pincode)) return;
    try {
      // Search for pincode via API
      const { searchLocations } = await import('./services/api');
      const res = await searchLocations(pincode, 'pincode');
      if (res.results && res.results.length > 0) {
        const result = res.results[0];
        handleSelectSearchResult(result);
      }
    } catch (err) {
      console.warn('Pincode lookup failed:', err);
    }
  }, [handleSelectSearchResult]);

  // Phase 3: Listen for postMessage from parent iframe controller
  const lastPincodeRef = useRef<string>('');
  useEffect(() => {
    function onMessage(e: MessageEvent) {
      // Accept messages from same origin or localhost
      if (!e.origin.includes('localhost')) return;
      if (e.data && e.data.type === 'WP_PINCODE_UPDATE' && typeof e.data.pincode === 'string') {
        const pin = e.data.pincode.replace(/\D/g, '').slice(0, 6);
        if (pin.length === 6 && pin !== lastPincodeRef.current) {
          lastPincodeRef.current = pin;
          handlePincodeNavigation(pin);
        }
      }
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [handlePincodeNavigation]);

  // Reset Filters / Return to normal full-India heatmap
  const handleResetFilters = () => {
    setSelectedState('');
    setSelectedDistrict('');
    setView('state');
    setSelectedIdentifier('state:maharashtra');
    setTargetCoords({ lat: 22.9734, lon: 78.6569, zoom: 5 });
    handleSelectRegion('state:maharashtra');
  };

  const plasticYears = filtersData?.plastic_waste_years || ['2018-19', '2019-20', '2020-21', '2021-22', '2022-23'];

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-['Plus_Jakarta_Sans',sans-serif]">
      {/* Top Header */}
      <Header
        onSelectResult={handleSelectSearchResult}
        onClearSearch={handleResetFilters}
        onOpenInfo={() => setIsInfoModalOpen(true)}
        backendHealthy={backendHealthy}
      />

      {/* Error Alert Banner */}
      {errorMessage && (
        <div className="bg-rose-50 border-b border-rose-200 px-4 py-2 text-rose-800 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600" />
            <span>{errorMessage}</span>
          </div>
          <button
            onClick={loadHeatmap}
            className="flex items-center gap-1 font-semibold text-rose-700 hover:text-rose-900 ml-4 underline"
          >
            <RefreshCw className="w-3 h-3" /> Retry
          </button>
        </div>
      )}

      {/* Main Workspace Layout */}
      <main className="flex-1 max-w-[1600px] w-full mx-auto p-3 sm:p-4 grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left Column: Regional Search & Control Panel */}
        <div className="lg:col-span-3 xl:col-span-3 space-y-4 max-h-[calc(100vh-90px)] overflow-y-auto pr-1">
          <SearchPanel
            onSelectResult={handleSelectSearchResult}
            onClearSearch={handleResetFilters}
          />
          <ControlPanel
            mode={mode}
            onModeChange={setMode}
            view={view}
            onViewChange={setView}
            metricType={metricType}
            onMetricTypeChange={setMetricType}
            plasticYear={plasticYear}
            onPlasticYearChange={setPlasticYear}
            plasticYears={plasticYears}
          />
        </div>

        {/* Center Column: Interactive Map */}
        <div className="lg:col-span-5 xl:col-span-5 h-[550px] lg:h-[calc(100vh-100px)] min-h-[500px]">
          <MapComponent
            geoJsonData={geoJsonData}
            mode={mode}
            view={view}
            selectedIdentifier={selectedIdentifier}
            onSelectRegion={handleSelectRegion}
            isLoading={isMapLoading}
            targetCoords={targetCoords}
          />
        </div>

        {/* Right Column: Details & Intelligence Panel */}
        <div className="lg:col-span-4 xl:col-span-4">
          <DetailsPanel
            details={regionDetails}
            onClose={() => setRegionDetails(null)}
            activeMode={mode}
            isLoading={isDetailsLoading}
          />
        </div>
      </main>

      {/* Sources & Methodology Modal */}
      <InfoModal
        isOpen={isInfoModalOpen}
        onClose={() => setIsInfoModalOpen(false)}
        sourcesData={sourcesData}
        methodologyData={methodologyData}
      />

      {/* Phase 4: Mandatory disclaimer banner */}
      <footer className="bg-amber-50 border-t border-amber-200 px-4 py-2 text-center">
        <p className="text-[11px] text-amber-800 font-medium">
          ⚠ <strong>Data Integrity Notice:</strong> District-level statistics displayed across matched PIN-code boundaries; values are not PIN-code-specific.
          Karnataka data sourced from DMA / Urban Development Dept, GoK. All-India data from CPCB (Solid Waste 2020-21, Plastic Waste 2018-23).
        </p>
      </footer>
    </div>
  );
};

export default App;
