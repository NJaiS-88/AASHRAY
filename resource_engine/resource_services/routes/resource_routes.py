from fastapi import APIRouter, HTTPException

from resource_services.schemas.allocation import (
    AllocationRequest,
    AllocationResult,
    IncidentAllocationRequest,
)
from resource_services.services.resource_requirement_service import (
    ResourceRequirementService,
)
from resource_services.services.resource_allocation_service import (
    ResourceAllocationService,
)


router = APIRouter(
    prefix="/resource",
    tags=["Resource Engine"],
)


REQUIREMENT_RULES_PATH = "resource_services/config/resource_rules.json"
WAREHOUSES_PATH = "resource_services/database/warehouses.json"


@router.post("/allocate", response_model=AllocationResult)
def allocate_resources(incident: IncidentAllocationRequest):
    try:
        requirement_service = ResourceRequirementService(
            REQUIREMENT_RULES_PATH
        )

        requirement_result = requirement_service.calculate(incident)

        allocation_service = ResourceAllocationService(
            WAREHOUSES_PATH,
            REQUIREMENT_RULES_PATH,
        )

        allocation_result = allocation_service.allocate(
            incident_id=incident.incident_id,
            requirements=requirement_result.requirements,
            severity=incident.severity,
            urgency=incident.urgency,
            priority=incident.priority,
        )

        return allocation_result

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Resource allocation failed: {str(error)}",
        )


@router.post("/allocate/batch", response_model=list[AllocationResult])
def allocate_resources_for_multiple_incidents(
    incidents: list[IncidentAllocationRequest],
):
    try:
        requirement_service = ResourceRequirementService(
            REQUIREMENT_RULES_PATH
        )

        allocation_service = ResourceAllocationService(
            WAREHOUSES_PATH,
            REQUIREMENT_RULES_PATH,
        )

        allocation_requests = [
            AllocationRequest(
                incident_id=incident.incident_id,
                requirements=requirement_service.calculate(
                    incident
                ).requirements,
                severity=incident.severity,
                urgency=incident.urgency,
                priority=incident.priority,
            )
            for incident in incidents
        ]

        # Results come back in allocation order: highest overall
        # priority score first.
        return allocation_service.allocate_batch(allocation_requests)

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Resource allocation failed: {str(error)}",
        )
