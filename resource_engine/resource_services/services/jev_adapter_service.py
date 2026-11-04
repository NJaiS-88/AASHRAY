from resource_services.schemas.allocation import PriorityLevel
from resource_services.schemas.jev_input import JevOrchestrationRequest
from resource_services.schemas.orchestration import OrchestrationRequest

JEV_PRIORITY_MAP: dict[str, PriorityLevel] = {
    "P1": "CRITICAL",
    "P2": "HIGH",
    "P3": "MODERATE",
    "P4": "LOW",
}

JEV_SCOPE_MAP: dict[str, str] = {
    "wide": "wide_area",
    "localized": "localized",
    "ambiguous": "ambiguous",
}


def jev_to_orchestration_request(
    jev_request: JevOrchestrationRequest,
) -> OrchestrationRequest:
    triage = jev_request.jev_triage
    assessment = triage.assessment

    severity = assessment.severity.numeric / 3.0
    urgency = assessment.urgency.numeric / 3.0

    priority_code = assessment.priority.level.upper()
    priority = JEV_PRIORITY_MAP.get(priority_code, "MODERATE")

    scope = None
    if triage.wide_area:
        scope = JEV_SCOPE_MAP.get(triage.wide_area.status, "ambiguous")

    selected_resource_ids = [
        item.resource for item in triage.selected_resources
    ]

    hazard_details = jev_request.hazard_details or getattr(triage, "hazard_details", []) or []

    return OrchestrationRequest(
        incident_id=jev_request.incident_id,
        incident_type=triage.incident_type,
        location=jev_request.location,
        locality=jev_request.locality,
        severity=severity,
        estimated_duration_hours=jev_request.estimated_duration_hours,
        patient_present=jev_request.patient_present,
        incident_scope=scope,
        selected_resource_ids=selected_resource_ids or None,
        urgency=urgency,
        priority=priority,
        hazard_details=hazard_details,
    )
