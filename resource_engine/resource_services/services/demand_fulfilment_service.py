from uuid import uuid4

from resource_services.schemas.demand_fulfilment import (
    DemandFulfilmentRequest,
    DemandFulfilmentResult,
    ResourceFulfilmentStatus,
)


class DemandFulfilmentService:

    def verify(
        self,
        request: DemandFulfilmentRequest,
    ) -> DemandFulfilmentResult:

        resource_status = {}
        total_shortage = {}

        for resource, required in request.required_resources.items():

            allocated = request.allocated_resources.get(
                resource,
                0.0,
            )

            shortage = max(required - allocated, 0.0)

            if shortage == 0:
                status = "FULFILLED"
            else:
                status = "SHORTAGE"

            resource_status[resource] = ResourceFulfilmentStatus(
                required=required,
                allocated=allocated,
                shortage=shortage,
                status=status,
            )

            total_shortage[resource] = shortage

        if all(shortage == 0 for shortage in total_shortage.values()):
            fulfilment_status = "FULLY_FULFILLED"
        else:
            fulfilment_status = "PARTIALLY_FULFILLED"

        return DemandFulfilmentResult(
            verification_id=f"VERIFY-{uuid4().hex[:8].upper()}",
            incident_id=request.incident_id,
            allocation_id=request.allocation_id,
            fulfilment_status=fulfilment_status,
            resource_status=resource_status,
            total_shortage=total_shortage,
        )