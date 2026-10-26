import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import type { HeatmapMode, GranularityView } from '../types';
import { RotateCcw, ZoomIn, ZoomOut, Layers } from 'lucide-react';

interface MapComponentProps {
  geoJsonData: any;
  mode: HeatmapMode;
  view: GranularityView;
  selectedIdentifier?: string;
  onSelectRegion: (id: string) => void;
  isLoading: boolean;
  targetCoords?: { lat: number; lon: number; zoom?: number } | null;
}

// Color scale interpolators
// Color scale interpolators
function getColorForValue(mode: HeatmapMode, val: number | null | undefined): string {
  if (val === null || val === undefined) {
    return '#e2e8f0'; // Slate-200 for unavailable
  }

  if (mode === 'waste_generation') {
    // Range: 0 to 23,000 TPD (State level up to 23k, District level 40 - 5,500 TPD)
    if (val > 15000) return '#b91c1c'; // Deep Red
    if (val > 10000) return '#ea580c'; // Orange-Red
    if (val > 6000) return '#f59e0b';  // Amber
    if (val > 2500) return '#84cc16';  // Lime
    if (val > 1000) return '#10b981';  // Emerald
    if (val > 300) return '#34d399';   // Medium Mint
    return '#6ee7b7';                  // Light Mint
  }

  if (mode === 'processing_gap') {
    // Range: 0 to 13,000 TPD
    if (val > 8000) return '#7e22ce'; // Deep Purple (severe gap)
    if (val > 4500) return '#dc2626'; // Red
    if (val > 2000) return '#f97316'; // Orange
    if (val > 500) return '#facc15';  // Yellow
    if (val > 0) return '#34d399';    // Emerald
    return '#10b981';                 // Zero gap - 100% treated!
  }

  if (mode === 'waste_to_energy') {
    // Range: 0 to 55 MW
    if (val > 35) return '#312e81'; // Deep Indigo
    if (val > 20) return '#2563eb'; // Blue
    if (val > 10) return '#0284c7'; // Sky
    if (val > 3) return '#06b6d4';  // Cyan
    return '#a5f3fc';               // Light Cyan
  }

  if (mode === 'waste_composition') {
    // CPCB Baseline
    return '#0d9488'; // Teal
  }

  return '#94a3b8';
}

export const MapComponent: React.FC<MapComponentProps> = ({
  geoJsonData,
  mode,
  view,
  selectedIdentifier,
  onSelectRegion,
  isLoading,
  targetCoords,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const geoJsonLayerRef = useRef<L.GeoJSON | null>(null);

  // Initialize Map
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    // Centered on India
    const map = L.map(mapContainerRef.current, {
      center: [22.9734, 78.6569],
      zoom: 5,
      minZoom: 4,
      maxZoom: 14,
      zoomControl: false,
    });

    // OpenStreetMap Standard Tiles (Crisp, clean, no API key required)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      subdomains: 'abc',
      maxZoom: 19,
    }).addTo(map);

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  const searchMarkerRef = useRef<L.CircleMarker | null>(null);

  // Fly to target coordinates and show pinpoint marker when searched or selected
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (searchMarkerRef.current) {
      map.removeLayer(searchMarkerRef.current);
      searchMarkerRef.current = null;
    }

    if (!targetCoords || targetCoords.lat === null || targetCoords.lon === null) return;

    const marker = L.circleMarker([targetCoords.lat, targetCoords.lon], {
      radius: 8,
      fillColor: '#0284c7',
      color: '#ffffff',
      weight: 2.5,
      opacity: 1,
      fillOpacity: 0.95,
    }).addTo(map);

    searchMarkerRef.current = marker;

    map.flyTo([targetCoords.lat, targetCoords.lon], targetCoords.zoom || 11, {
      duration: 1.4,
      easeLinearity: 0.25,
    });
  }, [targetCoords]);

  // Update GeoJSON Layer
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !geoJsonData) return;

    // Remove existing layer
    if (geoJsonLayerRef.current) {
      map.removeLayer(geoJsonLayerRef.current);
    }

    const isPincodeView = view === 'pincode' || geoJsonData.metadata?.view === 'pincode';

    const geoJsonLayer = L.geoJSON(geoJsonData, {
      style: (feature) => {
        if (!feature) return {};
        const props = feature.properties || {};
        const isSelected =
          selectedIdentifier &&
          (props.state === selectedIdentifier ||
            props.pincode === selectedIdentifier ||
            `pincode:${props.pincode}` === selectedIdentifier ||
            `state:${props.state?.toLowerCase()}` === selectedIdentifier?.toLowerCase() ||
            feature.id === selectedIdentifier);

        const val = props.value;
        const fillColor = getColorForValue(mode, val);

        return {
          fillColor: fillColor,
          weight: isSelected ? 3 : isPincodeView ? 1 : 1.5,
          opacity: 1,
          color: isSelected ? '#0f172a' : isPincodeView ? '#94a3b8' : '#ffffff',
          dashArray: !props.data_available && !isPincodeView ? '3, 4' : '',
          fillOpacity: isSelected ? 0.88 : isPincodeView ? 0.72 : 0.78,
        };
      },
      onEachFeature: (feature, layer) => {
        const props = feature.properties || {};
        const name = props.name || props.office_name || props.state || 'Region';
        const pincode = props.pincode;
        const val = props.value;
        const unit = props.unit || '';
        const metricLabel = props.metric_label || 'Value';
        const isDistrictLevel = props.is_district_level_stat;

        // Custom Tooltip HTML
        let tooltipContent = '';
        if (isPincodeView) {
          if (isDistrictLevel && val !== null && val !== undefined) {
            tooltipContent = `
              <div class="space-y-1">
                <div class="font-bold text-white text-xs flex items-center justify-between gap-3">
                  <span>PIN ${pincode || 'Postal Area'}</span>
                  <span class="text-[10px] px-1.5 py-0.2 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">District Statistic</span>
                </div>
                <div class="text-[11px] text-slate-300">${name} (${props.district || ''}, ${props.state || ''})</div>
                <div class="text-[10px] text-emerald-300 font-semibold border-t border-slate-700/60 pt-1 mt-1 flex justify-between">
                  <span>${metricLabel}:</span>
                  <span>${val.toLocaleString()} ${unit}</span>
                </div>
                <div class="text-[9.5px] text-slate-400 italic">
                  District-level measurement from DMA Karnataka displayed on PIN boundary.
                </div>
              </div>
            `;
          } else {
            tooltipContent = `
              <div class="space-y-1">
                <div class="font-bold text-white text-xs flex items-center justify-between gap-3">
                  <span>PIN ${pincode || 'Postal Area'}</span>
                  <span class="text-[10px] px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">PIN Boundary</span>
                </div>
                <div class="text-[11px] text-slate-300">${name} (${props.district || ''}, ${props.state || ''})</div>
                <div class="text-[10px] text-slate-400 border-t border-slate-700/60 pt-1 mt-1">
                  Local PIN waste: <span class="text-amber-400 font-semibold">Not Reported</span>
                </div>
                <div class="text-[10px] text-slate-400">
                  Parent State (${props.state}): ${props.parent_state_stats?.solid_generated_tpd?.toLocaleString() || 'N/A'} TPD
                </div>
              </div>
            `;
          }
        } else {
          const formattedVal = val !== null && val !== undefined ? `${val.toLocaleString()} ${unit}` : 'Data Unavailable';
          tooltipContent = `
            <div class="space-y-1">
              <div class="font-bold text-white text-xs flex items-center justify-between gap-3">
                <span>${name}</span>
                <span class="text-[10px] px-1.5 py-0.2 rounded ${
                  props.data_available
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                    : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                }">${props.data_available ? 'Reported' : 'Unavailable'}</span>
              </div>
              <div class="text-[11px] text-slate-300 flex items-center justify-between gap-2">
                <span>${metricLabel}:</span>
                <span class="font-bold text-emerald-400">${formattedVal}</span>
              </div>
              ${
                props.summary?.processing_gap_tpd !== undefined
                  ? `<div class="text-[10px] text-slate-400 border-t border-slate-700/60 pt-1 mt-1 flex justify-between">
                      <span>Gap:</span>
                      <span class="text-amber-300 font-medium">${props.summary.processing_gap_tpd?.toLocaleString() || 'NA'} TPD (${props.summary.processing_gap_pct || '0'}%)</span>
                    </div>`
                  : ''
              }
            </div>
          `;
        }

        layer.bindTooltip(tooltipContent, {
          className: 'custom-map-tooltip',
          sticky: true,
          direction: 'auto',
        });

        // Click interaction
        layer.on({
          click: () => {
            const id = props.pincode ? `pincode:${props.pincode}` : (props.state || feature.id);
            if (id) {
              onSelectRegion(id);
            }
          },
          mouseover: (e) => {
            const target = e.target;
            target.setStyle({
              weight: 3,
              color: '#0f172a',
              fillOpacity: 0.92,
            });
            if (!L.Browser.ie && !L.Browser.opera && !L.Browser.edge) {
              target.bringToFront();
            }
          },
          mouseout: (e) => {
            geoJsonLayer.resetStyle(e.target);
          },
        });
      },
    }).addTo(map);

    geoJsonLayerRef.current = geoJsonLayer;

    // Auto-fit bounds if features exist and not already focused on searched coordinates
    if (geoJsonData.features && geoJsonData.features.length > 0 && !targetCoords) {
      const bounds = geoJsonLayer.getBounds();
      if (bounds.isValid()) {
        map.fitBounds(bounds, {
          padding: [24, 24],
          maxZoom: isPincodeView ? 11 : 6,
          animate: true,
        });
      }
    }
  }, [geoJsonData, mode, view, selectedIdentifier, onSelectRegion, targetCoords]);

  const handleResetZoom = () => {
    if (mapInstanceRef.current) {
      mapInstanceRef.current.setView([22.9734, 78.6569], 5, { animate: true });
    }
  };

  const handleZoomIn = () => {
    if (mapInstanceRef.current) mapInstanceRef.current.zoomIn();
  };

  const handleZoomOut = () => {
    if (mapInstanceRef.current) mapInstanceRef.current.zoomOut();
  };

  return (
    <div className="relative w-full h-full min-h-[520px] rounded-2xl overflow-hidden border border-slate-200/90 shadow-sm bg-slate-100">
      <div ref={mapContainerRef} className="w-full h-full" />

      {/* Floating Map Controls */}
      <div className="absolute top-4 right-4 z-20 flex flex-col gap-1.5 bg-white/90 backdrop-blur-md p-1 rounded-xl border border-slate-200/80 shadow-md">
        <button
          onClick={handleZoomIn}
          className="p-2 text-slate-700 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors"
          title="Zoom In"
        >
          <ZoomIn className="w-4 h-4" />
        </button>
        <button
          onClick={handleZoomOut}
          className="p-2 text-slate-700 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors"
          title="Zoom Out"
        >
          <ZoomOut className="w-4 h-4" />
        </button>
        <div className="h-px bg-slate-200 my-0.5" />
        <button
          onClick={handleResetZoom}
          className="p-2 text-slate-700 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors"
          title="Reset to All India"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
      </div>

      {/* View Indicator Badge */}
      <div className="absolute bottom-4 left-4 z-20 bg-white/90 backdrop-blur-md px-3 py-1.5 rounded-xl border border-slate-200/80 shadow-sm flex items-center gap-2 text-xs font-semibold text-slate-800">
        <Layers className="w-3.5 h-3.5 text-emerald-600" />
        <span>
          {view === 'pincode' ? 'PIN-Code Boundaries Layer' : 'State Choropleth Layer'}
        </span>
        <span className="text-[10px] font-normal text-slate-500">
          ({geoJsonData?.features?.length || 0} features)
        </span>
      </div>

      {/* Loading Overlay */}
      {isLoading && (
        <div className="absolute inset-0 bg-white/60 backdrop-blur-xs z-30 flex items-center justify-center">
          <div className="bg-white px-4 py-3 rounded-2xl shadow-xl border border-slate-200/90 flex items-center gap-3">
            <div className="w-5 h-5 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin" />
            <span className="text-xs font-semibold text-slate-800">
              Rendering Geographic Geometry...
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export default MapComponent;
