from fastapi import APIRouter, HTTPException

from resource_services.schemas.agent_assignment import (
    AgentAssignmentRequest,
    AgentAssignmentResult,
)
from resource_services.services.agent_assignment_service import (
    AgentAssignmentService,
    NoResponderAvailableError,
)
from resource_services.services.mission_store import MissionStateError


router = APIRouter(
    prefix="/agent",
    tags=["Agent Assignment"],
)


RESPONDERS_PATH = "resource_services/database/responders.json"


@router.post(
    "/assign",
    response_model=AgentAssignmentResult,
)
def assign_agent(request: AgentAssignmentRequest):

    try:
        service = AgentAssignmentService(RESPONDERS_PATH)

        result = service.assign(request)

        return result

    except NoResponderAvailableError as error:
        # A valid request that cannot be served with the current responders.
        raise HTTPException(
            status_code=409,
            detail={
                "error": error.error_code,
                "message": str(error),
            },
        )

    except MissionStateError as error:
        # MISSION_ALREADY_CLOSED: the mission was completed or cancelled.
        raise HTTPException(
            status_code=409,
            detail={
                "error": error.error_code,
                "message": str(error),
            },
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Agent assignment failed: {str(error)}",
        )
