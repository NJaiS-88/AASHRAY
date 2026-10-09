from pydantic import BaseModel, Field


class ResourceRequirement(BaseModel):
    water: float = Field(ge=0)
    food: float = Field(ge=0)
    medical_kits: float = Field(ge=0)


class ResourceRequirementResult(BaseModel):
    incident_id: str
    requirements: ResourceRequirement