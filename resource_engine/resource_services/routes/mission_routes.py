from fastapi import APIRouter, HTTPException

from resource_services.schemas.mission import (
    MissionCreationRequest,
    MissionCreationResult,
)
from resource_services.schemas.mission_lifecycle import (
    MissionLifecycleResult,
)
from resource_services.services.mission_creation_service import (
    MissionCreationService,
)
from resource_services.services.mission_lifecycle_service import (
    MissionLifecycleService,
)
from resource_services.services.mission_store import MissionStateError


router = APIRouter(
    prefix="/mission",
    tags=["Mission Creation"],
)


# Completion and cancellation release responders, so they use the same
# responders.json as /agent/assign; missions.json sits next to it.
RESPONDERS_PATH = "resource_services/database/responders.json"


@router.post(
    "/create",
    response_model=MissionCreationResult,
)
def create_mission(request: MissionCreationRequest):

    try:
        service = MissionCreationService()

        result = service.create_mission(request)

        return result

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Mission creation failed: {str(error)}",
        )


@router.post(
    "/{mission_id}/complete",
    response_model=MissionLifecycleResult,
    tags=["Mission Lifecycle"],
)
def complete_mission(mission_id: str):

    try:
        service = MissionLifecycleService(RESPONDERS_PATH)

        return service.complete(mission_id)

    except MissionStateError as error:
        # Same convention as NO_RESPONDER_AVAILABLE on /agent/assign: a
        # valid request the mission's current state does not allow.
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
            detail=f"Mission completion failed: {str(error)}",
        )


@router.post(
    "/{mission_id}/cancel",
    response_model=MissionLifecycleResult,
    tags=["Mission Lifecycle"],
)
def cancel_mission(mission_id: str):

    try:
        service = MissionLifecycleService(RESPONDERS_PATH)

        return service.cancel(mission_id)

    except MissionStateError as error:
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
            detail=f"Mission cancellation failed: {str(error)}",
        )