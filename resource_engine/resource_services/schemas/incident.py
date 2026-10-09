from pydantic import BaseModel, Field
from .common import Location


class Locality(BaseModel):
    name: str
    population: int = Field(gt=0)
    population_density: float = Field(gt=0)
    affected_population: int = Field(gt=0)


class Incident(BaseModel):
    incident_id: str
    incident_type: str
    location: Location
    locality: Locality
    severity: float = Field(ge=0.0, le=1.0)
    estimated_duration_hours: float = Field(gt=0)
    patient_present: bool = False