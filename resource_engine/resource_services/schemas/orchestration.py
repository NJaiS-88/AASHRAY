from typing import Literal

from pydantic import BaseModel, Field

from resource_services.schemas.agent_assignment import AgentAssignmentResult
from resource_services.schemas.allocation import (
    AllocationResult,
    IncidentAllocationRequest,
)
from resource_services.schemas.common import Location
from resource_services.schemas.demand_fulfilment import DemandFulfilmentResult
from resource_services.schemas.mission import MissionCreationResult, RouteData
from resource_services.schemas.resource_requirement import (
    ResourceRequirementResult,
)


class OrchestrationRequest(IncidentAllocationRequest):
    # The existing Incident plus the two inputs Resource Allocation currently
    # requires: `urgency` and the categorical `priority`. No upstream service
    # produces them yet, so the caller supplies them explicitly (same shape
    # as POST /resource/allocate). The orchestrator never defaults them.
    pass


OrchestrationStage = Literal[
    "REQUIREMENT",
    "ALLOCATION",
    "DEMAND_FULFILMENT",
    "MISSION_CREATION",
    "AGENT_ASSIGNMENT",
    "ROUTE_ENGINE",
]


OrchestrationStatus = Literal[
    # Responder assigned and a route was planned.
    "COMPLETED",
    # Responder assigned; the Route Engine is not integrated yet.
    "ROUTE_ENGINE_NOT_CONNECTED",
    # Responder assigned; but no safe route exists due to hazards/closures.
    "NO_SAFE_ROUTE_FOUND",
    # NO_WAREHOUSE_PICKUP: Agent Assignment was not called.
    "MISSION_NOT_DISPATCHABLE",
    # Mission created, but no eligible responder.
    "NO_RESPONDER_AVAILABLE",
    # A stage raised an error; see `error.stage`.
    "FAILED",
]


class RoutePickup(BaseModel):
    warehouse_id: str
    location: Location


class RoutingInputs(BaseModel):
    # What the orchestrator hands to the Route Engine boundary.
    mission_id: str

    responder_id: str

    responder_location: Location

    # In pickup-sequence order.
    pickups: list[RoutePickup]

    destination: Location

    vehicle_type: str | None = None

    priority: str | None = None


class RouteBoundaryResult(BaseModel):
    status: Literal[
        "ROUTE_ENGINE_NOT_CONNECTED",
        "ROUTE_PLANNED",
        "NO_SAFE_ROUTE_FOUND",
    ]

    routing_inputs: RoutingInputs

    # Only set when a connected Route Engine returns a route.
    route: RouteData | None = None

    message: str | None = None


class OrchestrationError(BaseModel):
    # The stage where the pipeline stopped.
    stage: OrchestrationStage

    # NO_WAREHOUSE_PICKUP | NO_RESPONDER_AVAILABLE | STAGE_FAILED
    error_code: str

    message: str


class OrchestrationResult(BaseModel):
    orchestration_id: str
    incident_id: str

    status: OrchestrationStatus

    # From Demand Fulfilment, once it has run. Independent of `status`:
    # a PARTIALLY_FULFILLED mission is still dispatched.
    fulfilment_status: Literal[
        "FULLY_FULFILLED",
        "PARTIALLY_FULFILLED",
    ] | None = None

    # Stages that returned a result, in execution order.
    completed_stages: list[OrchestrationStage] = Field(default_factory=list)

    requirement: ResourceRequirementResult | None = None

    allocation: AllocationResult | None = None

    demand_fulfilment: DemandFulfilmentResult | None = None

    mission: MissionCreationResult | None = None

    agent_assignment: AgentAssignmentResult | None = None

    route: RouteBoundaryResult | None = None

    error: OrchestrationError | None = None
