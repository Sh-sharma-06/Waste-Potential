from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DataProvenance(BaseModel):
    source: str
    reporting_period: str
    agency: str
    granularity: str  # 'state', 'pincode', 'national_study'
    is_estimate: bool = False
    notes: Optional[str] = None


class SolidWasteStats(BaseModel):
    data_available: bool = True
    reason: Optional[str] = None
    generated_tpd: Optional[float] = None
    collected_tpd: Optional[float] = None
    treated_tpd: Optional[float] = None
    processing_gap_tpd: Optional[float] = None
    processing_gap_percentage: Optional[float] = None
    collection_efficiency_pct: Optional[float] = None
    treatment_efficiency_pct: Optional[float] = None
    provenance: Optional[DataProvenance] = None


class PlasticWasteStats(BaseModel):
    data_available: bool = True
    reason: Optional[str] = None
    historical_tpy: Dict[str, Optional[float]] = Field(default_factory=dict)
    latest_tpy: Optional[float] = None
    latest_period: Optional[str] = None
    trend: Optional[str] = None
    provenance: Optional[DataProvenance] = None


class WasteToEnergyStats(BaseModel):
    data_available: bool = True
    reason: Optional[str] = None
    theoretical_power_mw: Optional[float] = None
    treated_power_mw: Optional[float] = None
    conversion_parameters: Dict[str, Any] = Field(default_factory=dict)
    methodology: str = ""
    is_estimate: bool = True
    provenance: Optional[DataProvenance] = None


class WasteCompositionStats(BaseModel):
    data_available: bool = True
    granularity: str = "national_59_city_study"
    compostable_range_pct: List[float] = Field(default_factory=lambda: [40.0, 60.0])
    recyclable_range_pct: List[float] = Field(default_factory=lambda: [10.0, 25.0])
    inert_range_pct: List[float] = Field(default_factory=lambda: [25.0, 40.0])
    moisture_range_pct: List[float] = Field(default_factory=lambda: [30.0, 60.0])
    cn_ratio_range: List[float] = Field(default_factory=lambda: [20.0, 40.0])
    per_capita_generation_kg_day: List[float] = Field(default_factory=lambda: [0.12, 0.60])
    heavy_metals_mg_kg: Dict[str, str] = Field(default_factory=dict)
    limitations: str = ""
    provenance: Optional[DataProvenance] = None


class RegionDetails(BaseModel):
    identifier: str
    name: str
    region_type: str  # 'state' | 'pincode' | 'city' | 'district'
    geographic_level: str = "State / Union Territory"
    pincode: Optional[str] = None
    city: Optional[str] = None
    office_name: Optional[str] = None
    district: Optional[str] = None
    state: str
    circle: Optional[str] = None
    division: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    pincode_count: Optional[int] = None
    data_integrity_notice: str
    solid_waste: SolidWasteStats
    plastic_waste: PlasticWasteStats
    waste_to_energy: WasteToEnergyStats
    waste_composition: WasteCompositionStats
    state_context: Optional[Dict[str, Any]] = None
    city_study: Optional[Dict[str, Any]] = None
    district_waste_stats: Optional[Dict[str, Any]] = None


class FilterOptions(BaseModel):
    modes: List[Dict[str, str]]
    views: List[Dict[str, str]]
    states: List[str]
    districts_by_state: Dict[str, List[str]]
    plastic_waste_years: List[str]
