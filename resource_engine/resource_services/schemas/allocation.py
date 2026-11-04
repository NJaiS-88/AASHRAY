from typing import Literal

from pydantic import BaseModel, Field

from .incident import Incident


PriorityLevel = Literal[
    "LOW",
    "MODERATE",
    "HIGH",
    "CRITICAL",
]


class WarehouseAllocation(BaseModel):
    warehouse_id: str
    supplies: dict[str, float]


class AllocationRequest(BaseModel):
    incident_id: str

    requirements: dict[str, float]

    severity: float = Field(ge=0.0, le=1.0)

    urgency: float = Field(ge=0.0, le=1.0)

    priority: PriorityLevel


class IncidentAllocationRequest(Incident):
    urgency: float = Field(ge=0.0, le=1.0)

    priority: PriorityLevel


class AllocationResult(BaseModel):
    allocation_id: str
    incident_id: str

    required_resources: dict[str, float]

    warehouse_allocations: list[WarehouseAllocation]

    allocated_resources: dict[str, float]

    remaining_shortage: dict[str, float]

    allocation_status: str

    normalized_priority: float

    overall_priority_score: float

    final_priority_level: PriorityLevel
