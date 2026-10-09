from resource_services.schemas.incident import Incident
from resource_services.services.resource_requirement_service import (
    ResourceRequirementService,
)


def test_population_based_resource_requirement():
    incident = Incident(
        incident_id="INC-001",
        incident_type="FLOOD",
        location={
            "latitude": 19.0760,
            "longitude": 72.8777,
        },
        locality={
            "name": "Test Locality",
            "population": 18000,
            "population_density": 12000,
            "affected_population": 1000,
        },
        severity=0.8,
        estimated_duration_hours=12,
    )

    service = ResourceRequirementService(
        "resource_services/config/resource_rules.json"
    )

    result = service.calculate(incident)

    assert result.incident_id == "INC-001"

    assert result.requirements.water == 2000
    assert result.requirements.food == 1000
    assert result.requirements.medical_kits == 50