"""Data Contracts and Schemas for PlanIT Control FastAPI endpoints."""

from typing import Any, Dict, List, Optional
try:
    from pydantic import BaseModel, Field
except ImportError:
    from dataclasses import dataclass, field as Field, asdict
    class BaseModel:
        def model_dump(self):
            return asdict(self)


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    model_version: str
    monitored_sites_count: int
    active_stream_subscribers: int


class SiteSummaryResponse(BaseModel):
    plant_id: int
    plant_name: str
    utility_name: str
    county: str
    latitude: float
    longitude: float
    capacity_mw: float
    technology: str
    fema_flood_zone: str
    is_sfha: bool
    latest_hazard_index: Optional[float] = None
    operational_status: Optional[str] = "NORMAL"


class SiteDetailResponse(BaseModel):
    plant_id: int
    plant_name: str
    utility_name: str
    county: str
    latitude: float
    longitude: float
    capacity_mw: float
    hazard_index: float
    primary_hazard: str
    probabilities: Dict[str, float]
    operational_status: str
    alert_message: str
    live_telemetry: Dict[str, Any]
    fema_flood_risk: Dict[str, Any]
    active_nws_warnings: List[Dict[str, Any]]


class SimulationRequest(BaseModel):
    external_strike_miles: Optional[float] = None
    hypothetical_temp_f: Optional[float] = None
    hypothetical_rain_mm: Optional[float] = None


class CrewReportCreate(BaseModel):
    plant_id: int
    reported_by: str
    hazard_type: str  # Wildlife, Flood, Lightning, Heat, Debris/Muck
    description: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    photo_url: Optional[str] = None


class CrewReportResponse(BaseModel):
    report_id: int
    status: str
    message: str
    timestamp: str


class RetrainStatusResponse(BaseModel):
    timestamp: str
    historical_samples: int
    new_stream_samples: int
    total_samples: int
    validation_macro_f1: float
    validation_macro_auc: float
    hot_swapped: bool
    classes: List[str]
