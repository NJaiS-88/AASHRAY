from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from resource_services.schemas.orchestration import (
    OrchestrationRequest,
    OrchestrationResult,
)
from resource_services.services.orchestration_service import (
    OrchestrationService,
)


router = APIRouter(
    tags=["Orchestration"],
)


REQUIREMENT_RULES_PATH = "resource_services/config/resource_rules.json"
WAREHOUSES_PATH = "resource_services/database/warehouses.json"
RESPONDERS_PATH = "resource_services/database/responders.json"


# Same conventions as the existing routes: 409 for a valid request that
# cannot be served (as NO_RESPONDER_AVAILABLE on /agent/assign), 500 for a
# failure. The body is always the full OrchestrationResult so the outputs of
# the stages that did run are not lost.
HTTP_STATUS_BY_RESULT = {
    "COMPLETED": 200,
    "ROUTE_ENGINE_NOT_CONNECTED": 200,
    "NO_SAFE_ROUTE_FOUND": 409,
    "MISSION_NOT_DISPATCHABLE": 409,
    "NO_RESPONDER_AVAILABLE": 409,
    "FAILED": 500,
}


@router.post(
    "/orchestrate",
    response_model=OrchestrationResult,
    responses={
        409: {"model": OrchestrationResult},
        500: {"model": OrchestrationResult},
    },
)
def orchestrate(request: OrchestrationRequest):

    try:
        service = OrchestrationService(
            REQUIREMENT_RULES_PATH,
            WAREHOUSES_PATH,
            RESPONDERS_PATH,
        )

        result = service.run(request)

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Orchestration failed: {str(error)}",
        )

    return JSONResponse(
        status_code=HTTP_STATUS_BY_RESULT[result.status],
        content=result.model_dump(mode="json"),
    )
