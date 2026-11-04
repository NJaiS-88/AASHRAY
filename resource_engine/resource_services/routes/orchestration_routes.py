import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from resource_services.schemas.jev_input import JevOrchestrationRequest
from resource_services.schemas.orchestration import (
    OrchestrationRequest,
    OrchestrationResult,
)
from resource_services.services.jev_adapter_service import (
    jev_to_orchestration_request,
)
from resource_services.services.orchestration_service import (
    OrchestrationService,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Orchestration"],
)

REQUIREMENT_RULES_PATH = "resource_services/config/resource_rules_v2.json"
WAREHOUSES_PATH = "resource_services/database/warehouses.json"
RESPONDERS_PATH = "resource_services/database/responders.json"
LIVE_ORCHESTRATIONS_PATH = Path("resource_services/database/live_orchestrations.json")

HTTP_STATUS_BY_RESULT = {
    "COMPLETED": 200,
    "ROUTE_ENGINE_NOT_CONNECTED": 200,
    "NO_SAFE_ROUTE_FOUND": 409,
    "MISSION_NOT_DISPATCHABLE": 409,
    "NO_RESPONDER_AVAILABLE": 409,
    "FAILED": 500,
}


def _save_live_orchestration(request: OrchestrationRequest, result: OrchestrationResult):
    try:
        entries = []
        if LIVE_ORCHESTRATIONS_PATH.exists():
            try:
                with open(LIVE_ORCHESTRATIONS_PATH, "r", encoding="utf-8") as f:
                    entries = json.load(f)
            except Exception:
                entries = []

        item = {
            "incident_id": request.incident_id,
            "incident_type": request.incident_type,
            "locality_name": request.locality.name,
            "latitude": str(request.location.latitude),
            "longitude": str(request.location.longitude),
            "population": str(request.locality.population),
            "population_density": str(request.locality.population_density),
            "affected_population": str(request.locality.affected_population),
            "severity": str(round(request.severity, 2)),
            "urgency": str(round(request.urgency, 2)),
            "priority": str(request.priority),
            "estimated_duration_hours": str(request.estimated_duration_hours),
            "patient_present": str(request.patient_present).lower(),
            "hazard_details": getattr(request, "hazard_details", []) or [],
            "status": result.status,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "is_live": True,
            "full_orchestration": result.model_dump(mode="json"),
        }

        filtered = [e for e in entries if e.get("incident_id") != request.incident_id]
        filtered.insert(0, item)
        LIVE_ORCHESTRATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LIVE_ORCHESTRATIONS_PATH, "w", encoding="utf-8") as f:
            json.dump(filtered[:30], f, indent=2)
    except Exception as e:
        logger.warning(f"Could not persist live orchestration: {e}")


def _run_orchestration(request: OrchestrationRequest) -> JSONResponse:
    try:
        service = OrchestrationService(
            REQUIREMENT_RULES_PATH,
            WAREHOUSES_PATH,
            RESPONDERS_PATH,
        )

        result = service.run(request)

        # Persist all live missions (from JEV or dashboard execution)
        _save_live_orchestration(request, result)

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Orchestration failed: {str(error)}",
        )

    return JSONResponse(
        status_code=HTTP_STATUS_BY_RESULT[result.status],
        content=result.model_dump(mode="json"),
    )


@router.post(
    "/orchestrate",
    response_model=OrchestrationResult,
    responses={
        409: {"model": OrchestrationResult},
        500: {"model": OrchestrationResult},
    },
)
def orchestrate(request: OrchestrationRequest):
    return _run_orchestration(request)


@router.post(
    "/orchestrate/from-jev",
    response_model=OrchestrationResult,
    responses={
        409: {"model": OrchestrationResult},
        500: {"model": OrchestrationResult},
    },
)
def orchestrate_from_jev(request: JevOrchestrationRequest):
    orchestration_request = jev_to_orchestration_request(request)
    return _run_orchestration(orchestration_request)


@router.get("/orchestrate/live-missions")
def get_live_missions():
    if not LIVE_ORCHESTRATIONS_PATH.exists():
        return {"live_missions": []}
    try:
        with open(LIVE_ORCHESTRATIONS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"live_missions": data}
    except Exception:
        return {"live_missions": []}


@router.post("/orchestrate/reset-fleet")
def reset_fleet():
    with open(RESPONDERS_PATH, "r", encoding="utf-8") as f:
        responders = json.load(f)
    for r in responders:
        r["status"] = "AVAILABLE"
    with open(RESPONDERS_PATH, "w", encoding="utf-8") as f:
        json.dump(responders, f, indent=2)
    return {"status": "success", "message": "All fleet responders reset to AVAILABLE"}


@router.post("/orchestrate/reset-test-data")
def reset_test_data():
    import os
    if os.getenv("ENVIRONMENT") == "production":
        raise HTTPException(
            status_code=403,
            detail="Test data reset is strictly prohibited in production environment."
        )

    # 1. Clear disposable live orchestrations
    LIVE_ORCHESTRATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LIVE_ORCHESTRATIONS_PATH, "w", encoding="utf-8") as f:
        json.dump([], f, indent=2)

    # 2. Reset fleet responders to AVAILABLE
    with open(RESPONDERS_PATH, "r", encoding="utf-8") as f:
        responders = json.load(f)
    for r in responders:
        r["status"] = "AVAILABLE"
    with open(RESPONDERS_PATH, "w", encoding="utf-8") as f:
        json.dump(responders, f, indent=2)

    return {
        "status": "success",
        "message": "Development test data reset successfully. Dashboard restored to 5 default scenarios."
    }
