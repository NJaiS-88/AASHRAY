from pydantic import BaseModel, Field


class ResourceRequirementResult(BaseModel):
    incident_id: str
    requirements: dict[str, float]
    selected_resource_ids: list[str] = Field(default_factory=list)
    calculation_details: dict[str, dict] = Field(default_factory=dict)
