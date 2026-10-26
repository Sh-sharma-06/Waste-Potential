import type { FilterOptions, HeatmapMode, GranularityView, RegionDetails, SearchResult, SearchResponse } from '../types';

const API_BASE = '/api';

export async function fetchHealth(): Promise<any> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error('Health check failed');
  return res.json();
}

export async function fetchFilters(): Promise<FilterOptions> {
  const res = await fetch(`${API_BASE}/filters`);
  if (!res.ok) throw new Error('Failed to load filters');
  return res.json();
}

export async function fetchSources(): Promise<any> {
  const res = await fetch(`${API_BASE}/sources`);
  if (!res.ok) throw new Error('Failed to load sources');
  return res.json();
}

export async function fetchMethodology(): Promise<any> {
  const res = await fetch(`${API_BASE}/methodology`);
  if (!res.ok) throw new Error('Failed to load methodology');
  return res.json();
}

export async function fetchHeatmapData(params: {
  mode: HeatmapMode;
  view: GranularityView;
  state?: string;
  district?: string;
  pincode?: string;
  metricType?: 'solid' | 'plastic';
  plasticYear?: string;
}): Promise<any> {
  const q = new URLSearchParams();
  q.set('mode', params.mode);
  q.set('view', params.view);
  if (params.state) q.set('state', params.state);
  if (params.district) q.set('district', params.district);
  if (params.pincode) q.set('pincode', params.pincode);
  if (params.metricType) q.set('metric_type', params.metricType);
  if (params.plasticYear) q.set('plastic_year', params.plasticYear);

  const res = await fetch(`${API_BASE}/heatmap?${q.toString()}`);
  if (!res.ok) throw new Error(`Failed to load heatmap data (${res.status})`);
  return res.json();
}

export async function fetchRegionDetails(identifier: string): Promise<RegionDetails> {
  const res = await fetch(`${API_BASE}/heatmap/details/${encodeURIComponent(identifier)}`);
  if (!res.ok) throw new Error(`Failed to load region details (${res.status})`);
  return res.json();
}

export async function searchRegions(query: string, type: string = 'all'): Promise<SearchResult[]> {
  if (!query || query.trim().length === 0) return [];
  const q = new URLSearchParams();
  q.set('q', query.trim());
  if (type) q.set('type', type);
  const res = await fetch(`${API_BASE}/search?${q.toString()}`);
  if (!res.ok) return [];
  const data: SearchResponse = await res.json();
  return data.results || [];
}

export async function searchLocations(query: string, type: string = 'all'): Promise<SearchResponse> {
  if (!query || query.trim().length === 0) {
    return { query, type, count: 0, results: [], error: 'Please enter a search query.' };
  }
  const q = new URLSearchParams();
  q.set('q', query.trim());
  if (type) q.set('type', type);
  const res = await fetch(`${API_BASE}/search?${q.toString()}`);
  if (!res.ok) {
    return { query, type, count: 0, results: [], error: `Server error (${res.status})` };
  }
  return res.json();
}
