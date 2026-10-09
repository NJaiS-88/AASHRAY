import logging
from pathlib import Path
from uuid import uuid4

from resource_services.schemas.agent_assignment import AgentAssignmentRequest
from resource_services.schemas.allocation import AllocationResult
from resource_services.schemas.demand_fulfilment import DemandFulfilmentRequest
from resource_services.schemas.mission import MissionCreationRequest
from resource_services.schemas.orchestration import (
    OrchestrationError,
    OrchestrationRequest,
    OrchestrationResult,
    OrchestrationStage,
    RoutePickup,
    RoutingInputs,
)
from resource_services.services.agent_assignment_service import (
    AgentAssignmentService,
    NoResponderAvailableError,
)
from resource_services.services.demand_fulfilment_service import (
    DemandFulfilmentService,
)
from resource_services.services.mission_creation_service import (
    MissionCreationService,
)
from resource_services.services.resource_allocation_service import (
    ResourceAllocationService,
)
from resource_services.services.resource_requirement_service import (
    ResourceRequirementService,
)
from resource_services.services.route_engine_client import RouteEngineClient


logger = logging.getLogger(__name__)


class OrchestrationService:
    # Runs the existing services in order:
    #
    #   Requirement -> Allocation -> Demand Fulfilment -> Mission Creation
    #     -> Agent Assignment -> Route Engine boundary
    #
    # It adapts to their current contracts and stops at the first stage
    # that cannot continue. It never mutates responder status itself:
    # Agent Assignment owns AVAILABLE -> BUSY.

    def __init__(
        self,
        requirement_rules_path: str | Path,
        warehouses_path: str | Path,
        responders_path: str | Path,
        route_engine_client: RouteEngineClient | None = None,
    ):
        self.requirement_rules_path = requirement_rules_path
        self.warehouses_path = warehouses_path
        self.responders_path = responders_path
        self.route_engine_client = route_engine_client or RouteEngineClient()

    def run(self, request: OrchestrationRequest) -> OrchestrationResult:

        result = OrchestrationResult(
            orchestration_id=f"ORCH-{uuid4().hex[:8].upper()}",
            incident_id=request.incident_id,
            status="FAILED",
        )

        # STEP 1 - Resource Requirement
        try:
            requirement = ResourceRequirementService(
                self.requirement_rules_path
            ).calculate(request)
        except Exception as error:
            return self._failed(result, "REQUIREMENT", error)

        result.requirement = requirement
        result.completed_stages.append("REQUIREMENT")

        # STEP 2 - Resource Allocation (urgency/priority come from the request)
        try:
            allocation_service = ResourceAllocationService(
                self.warehouses_path,
                self.requirement_rules_path,
            )

            allocation = allocation_service.allocate(
                incident_id=request.incident_id,
                requirements=requirement.requirements,
                severity=request.severity,
                urgency=request.urgency,
                priority=request.priority,
            )
        except Exception as error:
            return self._failed(result, "ALLOCATION", error)

        result.allocation = allocation
        result.completed_stages.append("ALLOCATION")

        # STEP 3 - Demand Fulfilment
        try:
            demand_fulfilment = DemandFulfilmentService().verify(
                DemandFulfilmentRequest(
                    allocation_id=allocation.allocation_id,
                    incident_id=allocation.incident_id,
                    required_resources=allocation.required_resources.model_dump(),
                    allocated_resources=allocation.allocated_resources.model_dump(),
                )
            )
        except Exception as error:
            return self._failed(result, "DEMAND_FULFILMENT", error)

        result.demand_fulfilment = demand_fulfilment
        result.fulfilment_status = demand_fulfilment.fulfilment_status
        result.completed_stages.append("DEMAND_FULFILMENT")

        # STEP 4 - Mission Creation
        try:
            mission_request = self._build_mission_request(
                request,
                allocation,
                allocation_service,
            )

            mission = MissionCreationService().create_mission(mission_request)
        except Exception as error:
            return self._failed(result, "MISSION_CREATION", error)

        result.mission = mission
        result.completed_stages.append("MISSION_CREATION")

        # RULE: no warehouse pickup -> not dispatchable. Agent Assignment is
        # not called, so no responder status changes.
        if not mission_request.warehouse_pickups:
            result.status = "MISSION_NOT_DISPATCHABLE"
            result.error = OrchestrationError(
                stage="AGENT_ASSIGNMENT",
                error_code="NO_WAREHOUSE_PICKUP",
                message=(
                    "Allocation produced no warehouse pickup, so there is no "
                    "pickup location to assign a responder to. Agent "
                    "Assignment was not called."
                ),
            )
            return result

        # STEP 5 - Agent Assignment (persists AVAILABLE -> BUSY itself)
        first_pickup = mission_request.warehouse_pickups[0]

        try:
            assignment = AgentAssignmentService(self.responders_path).assign(
                AgentAssignmentRequest(
                    mission_id=mission.mission_id,
                    required_responder_types=mission.required_responder_types,
                    first_warehouse_location=first_pickup.location,
                    first_warehouse_id=first_pickup.warehouse_id,
                )
            )
        except NoResponderAvailableError as error:
            result.status = "NO_RESPONDER_AVAILABLE"
            result.error = OrchestrationError(
                stage="AGENT_ASSIGNMENT",
                error_code=error.error_code,
                message=str(error),
            )
            return result
        except Exception as error:
            return self._failed(result, "AGENT_ASSIGNMENT", error)

        result.agent_assignment = assignment
        result.completed_stages.append("AGENT_ASSIGNMENT")

        # STEP 6 - Route Engine boundary
        # From here on the responder is BUSY. A route that is not connected
        # or fails does not undo the assignment: there is no mission
        # completion/cancellation lifecycle yet to release the responder.
        try:
            route = self.route_engine_client.plan_route(
                RoutingInputs(
                    mission_id=mission.mission_id,
                    responder_id=assignment.responder_id,
                    responder_location=assignment.responder_location,
                    pickups=[
                        RoutePickup(
                            warehouse_id=pickup.warehouse_id,
                            location=pickup.location,
                        )
                        for pickup in mission_request.warehouse_pickups
                    ],
                    destination=mission.destination,
                    vehicle_type=assignment.responder_type,
                    priority=allocation.final_priority_level,
                )
            )
        except Exception as error:
            return self._failed(result, "ROUTE_ENGINE", error)

        result.route = route
        result.completed_stages.append("ROUTE_ENGINE")

        if route.status == "ROUTE_PLANNED":
            result.status = "COMPLETED"
        elif route.status == "NO_SAFE_ROUTE_FOUND":
            result.status = "NO_SAFE_ROUTE_FOUND"
        else:
            result.status = "ROUTE_ENGINE_NOT_CONNECTED"

        return result

    def _build_mission_request(
        self,
        request: OrchestrationRequest,
        allocation: AllocationResult,
        allocation_service: ResourceAllocationService,
    ) -> MissionCreationRequest:

        # Pickup locations come from the existing warehouse data; an unknown
        # warehouse_id raises instead of inventing a location.
        locations = {
            warehouse.warehouse_id: warehouse.location
            for warehouse in allocation_service.warehouses
        }

        return MissionCreationRequest(
            incident_id=request.incident_id,
            destination=request.location,
            risk_score=request.severity,
            priority=allocation.final_priority_level,
            patient_present=request.patient_present,
            # MVP contract: the actually allocated resources.
            resources=allocation.allocated_resources.model_dump(),
            warehouse_pickups=[
                {
                    "warehouse_id": pickup.warehouse_id,
                    "location": locations[pickup.warehouse_id],
                    "supplies": pickup.supplies.model_dump(),
                }
                for pickup in allocation.warehouse_allocations
            ],
        )

    def _failed(
        self,
        result: OrchestrationResult,
        stage: OrchestrationStage,
        error: Exception,
    ) -> OrchestrationResult:

        logger.exception(
            "Orchestration %s stopped at %s",
            result.orchestration_id,
            stage,
        )

        result.status = "FAILED"
        result.error = OrchestrationError(
            stage=stage,
            error_code="STAGE_FAILED",
            message=f"{type(error).__name__}: {error}",
        )

        return result
