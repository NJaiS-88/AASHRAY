from pydantic import BaseModel, Field

from resource_services.schemas.common import Location
from resource_services.schemas.incident import Locality


class JevSeverity(BaseModel):
    numeric: int = Field(ge=0, le=3)


class JevUrgency(BaseModel):
    numeric: int = Field(ge=0, le=3)


class JevPriority(BaseModel):
    level: str


class JevAssessment(BaseModel):
    severity: JevSeverity
    urgency: JevUrgency
    priority: JevPriority


class JevSelectedResource(BaseModel):
    resource: str


class JevWideArea(BaseModel):
    status: str


class JevTriage(BaseModel):
    incident_type: str
    assessment: JevAssessment
    selected_resources: list[JevSelectedResource] = Field(default_factory=list)
    wide_area: JevWideArea | None = None
    hazard_details: list[str] = Field(default_factory=list)


class JevOrchestrationRequest(BaseModel):
    incident_id: str
    location: Location
    locality: Locality
    patient_present: bool = False
    estimated_duration_hours: float = Field(gt=0, default=24.0)
    hazard_details: list[str] = Field(default_factory=list)
    jev_triage: JevTriage
