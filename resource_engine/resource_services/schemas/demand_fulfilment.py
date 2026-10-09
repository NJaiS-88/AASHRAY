from pydantic import BaseModel, Field
from typing import Literal


class ResourceFulfilmentStatus(BaseModel):
    required: float = Field(ge=0)
    allocated: float = Field(ge=0)
    shortage: float = Field(ge=0)
    status: Literal["FULFILLED", "SHORTAGE"]


class DemandFulfilmentRequest(BaseModel):
    allocation_id: str
    incident_id: str

    required_resources: dict[str, float]
    allocated_resources: dict[str, float]


class DemandFulfilmentResult(BaseModel):
    verification_id: str
    incident_id: str
    allocation_id: str

    fulfilment_status: Literal[
        "FULLY_FULFILLED",
        "PARTIALLY_FULFILLED",
    ]

    resource_status: dict[str, ResourceFulfilmentStatus]

    total_shortage: dict[str, float]