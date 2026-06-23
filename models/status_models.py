from pydantic import BaseModel
from typing import Optional, Dict, List, Any


# ──────────────────────────────────────────────────────────────────────────────
# REQUEST MODELS
# ──────────────────────────────────────────────────────────────────────────────

class StatusRequest(BaseModel):
    """Generic status query request"""
    query: str


class AvailabilityRequest(BaseModel):
    """Availability query for time-series data"""
    query: str
    granularity: str = "daily"  # daily, weekly, monthly
    days: int = 7


class ServiceStatusRequest(BaseModel):
    """Service status query"""
    service_id: Optional[str] = None
    service_name: Optional[str] = None


class ImpactAnalysisRequest(BaseModel):
    """Root cause analysis request"""
    device_id: Optional[str] = None
    device_ip: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# RESPONSE MODELS
# ──────────────────────────────────────────────────────────────────────────────

class DeviceBreakdown(BaseModel):
    """Device classification breakdown"""
    OLT: int = 0
    ONT: int = 0
    Router: int = 0
    Switch: int = 0
    UPS: int = 0
    Other: int = 0


class LocationSummary(BaseModel):
    """District hierarchy counts derived from Status API inventory rows."""
    total_mandals: int = 0
    total_gram_panchayats: int = 0


class AggregatedStatus(BaseModel):
    """Compressed status summary for LLM"""
    entity_type: str  # DISTRICT, MANDAL, LOCATION, DEVICE, IP, SERVICE
    entity_name: str
    overall_health: str  # Healthy, Degraded, Critical
    total_devices: int
    devices_up: int
    devices_down: int
    availability: float  # percentage
    critical_alerts: int
    affected_services: int
    device_breakdown: DeviceBreakdown
    # Present for DISTRICT scope; omitted from smaller scope responses.
    location_summary: Optional[LocationSummary] = None
    top_issues: List[str] = []
    recommended_actions: List[str] = []


class StatusResponse(BaseModel):
    """Final response sent to LLM"""
    success: bool
    data: Optional[AggregatedStatus] = None
    error: Optional[str] = None
    raw_device_count: int = 0  # For context


class AvailabilityPoint(BaseModel):
    """Single time-series data point"""
    timestamp: str
    availability: float
    devices_up: int
    devices_down: int


class AvailabilityResponse(BaseModel):
    """Availability trend response"""
    entity: str
    granularity: str
    data: List[AvailabilityPoint]


class ServiceStatus(BaseModel):
    """Single service status"""
    service_id: str
    service_name: str
    status: str  # ACTIVE, AFFECTED, DOWN
    affected_devices: int
    affected_users: int


class ServiceStatusResponse(BaseModel):
    """Service status response"""
    services: List[ServiceStatus]
    total_affected: int


class DeviceImpact(BaseModel):
    """Impact of a single device on services"""
    device_id: str
    device_name: str
    services: List[Dict[str, Any]]


class ImpactAnalysisResponse(BaseModel):
    """Root cause analysis response"""
    device: DeviceImpact
    cascading_impact: List[Dict[str, Any]]
    estimated_affected_users: int
