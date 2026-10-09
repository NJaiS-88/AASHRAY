from typing import Literal

from pydantic import BaseModel, Field

from .incident import Incident
from .resource_requirement import ResourceRequirement


PriorityLevel = Literal[
    "LOW",
    "MODERATE",
    "HIGH",
    "CRITICAL",
]


class WarehouseAllocation(BaseModel):
    warehouse_id: str
    supplies: ResourceRequirement


class AllocationRequest(BaseModel):
    # One emergency entering the Resource Engine.
    # Severity and urgency will later be supplied by upstream services;
    # until those exist they are plain inputs to the engine.

    incident_id: str

    requirements: ResourceRequirement

    severity: float = Field(ge=0.0, le=1.0)

    urgency: float = Field(ge=0.0, le=1.0)

    priority: PriorityLevel


class IncidentAllocationRequest(Incident):
    # Route level input: an incident plus the priority inputs the
    # allocation decision now needs. Severity is inherited from Incident.

    urgency: float = Field(ge=0.0, le=1.0)

    priority: PriorityLevel


class AllocationResult(BaseModel):
    allocation_id: str
    incident_id: str

    required_resources: ResourceRequirement

    warehouse_allocations: list[WarehouseAllocation]

    allocated_resources: ResourceRequirement

    remaining_shortage: ResourceRequirement

    allocation_status: str

    normalized_priority: float

    overall_priority_score: float

    final_priority_level: PriorityLevel
