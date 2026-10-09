from fastapi import APIRouter, HTTPException

from resource_services.schemas.demand_fulfilment import (
    DemandFulfilmentRequest,
    DemandFulfilmentResult,
)
from resource_services.services.demand_fulfilment_service import (
    DemandFulfilmentService,
)


router = APIRouter(
    prefix="/demand",
    tags=["Demand Fulfilment"],
)


@router.post(
    "/verify",
    response_model=DemandFulfilmentResult,
)
def verify_demand(request: DemandFulfilmentRequest):

    try:
        service = DemandFulfilmentService()

        result = service.verify(request)

        return result

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Demand fulfilment verification failed: {str(error)}",
        )