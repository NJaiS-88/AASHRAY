from resource_services.schemas.incident import Incident
from resource_services.services.resource_requirement_service import (
    ResourceRequirementService,
)


RULES_PATH = "resource_services/config/resource_rules_v2.json"


def test_model_a_calculates_dynamic_resources():
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
        selected_resource_ids=["drinking_water", "food_dry_rations", "medicines_medical_supplies"],
    )

    service = ResourceRequirementService(RULES_PATH)

    result = service.calculate(incident, urgency=0.7)

    assert result.incident_id == "INC-001"
    assert len(result.requirements) == 3
    assert "drinking_water" in result.requirements
    assert "food_dry_rations" in result.requirements
    assert "medicines_medical_supplies" in result.requirements

    assert result.requirements["drinking_water"] > 0
    assert result.requirements["food_dry_rations"] > 0
    assert result.requirements["medicines_medical_supplies"] > 0

    assert "drinking_water" in result.calculation_details
    details = result.calculation_details["drinking_water"]
    assert details["quantity_basis"] == "per_person"
    assert details["demand_base"] == 1000.0
    assert details["adjustment_factor"] > 1.0


def test_legacy_resource_ids_are_mapped():
    incident = Incident(
        incident_id="INC-LEGACY",
        incident_type="FLOOD",
        location={"latitude": 19.0760, "longitude": 72.8777},
        locality={
            "name": "Test",
            "population": 5000,
            "population_density": 8000,
            "affected_population": 200,
        },
        severity=0.5,
        estimated_duration_hours=6,
        selected_resource_ids=["water", "food", "medical_kits"],
    )

    service = ResourceRequirementService(RULES_PATH)
    result = service.calculate(incident)

    assert "drinking_water" in result.requirements
    assert "food_dry_rations" in result.requirements
    assert "medicines_medical_supplies" in result.requirements


def test_cash_assistance_is_blocked():
    incident = Incident(
        incident_id="INC-CASH",
        incident_type="FLOOD",
        location={"latitude": 19.0760, "longitude": 72.8777},
        locality={
            "name": "Test",
            "population": 5000,
            "population_density": 8000,
            "affected_population": 200,
        },
        severity=0.9,
        estimated_duration_hours=24,
        selected_resource_ids=["cash_assistance"],
    )

    service = ResourceRequirementService(RULES_PATH)
    result = service.calculate(incident, urgency=0.9)

    assert result.requirements["cash_assistance"] == 0.0
    assert result.calculation_details["cash_assistance"]["blocked"] is True


def test_per_household_basis():
    incident = Incident(
        incident_id="INC-HH",
        incident_type="FLOOD",
        location={"latitude": 19.0760, "longitude": 72.8777},
        locality={
            "name": "Test",
            "population": 5000,
            "population_density": 8000,
            "affected_population": 100,
        },
        severity=0.5,
        estimated_duration_hours=12,
        selected_resource_ids=["water_purification"],
    )

    service = ResourceRequirementService(RULES_PATH)
    result = service.calculate(incident)

    details = result.calculation_details["water_purification"]
    assert details["quantity_basis"] == "per_household"
    # 100 people / 4.5 per household = ceil(22.22) = 23 households
    assert details["demand_base"] == 23


def test_fixed_team_basis():
    incident = Incident(
        incident_id="INC-TEAM",
        incident_type="FLOOD",
        location={"latitude": 19.0760, "longitude": 72.8777},
        locality={
            "name": "Test",
            "population": 50000,
            "population_density": 8000,
            "affected_population": 5000,
        },
        severity=0.9,
        estimated_duration_hours=24,
        selected_resource_ids=["search_and_rescue"],
    )

    service = ResourceRequirementService(RULES_PATH)
    result = service.calculate(incident, urgency=0.9)

    details = result.calculation_details["search_and_rescue"]
    assert details["quantity_basis"] == "fixed_team"
    assert details["demand_base"] == 1.0
    assert result.requirements["search_and_rescue"] == 1.0


def test_all_30_resources_calculated():
    incident = Incident(
        incident_id="INC-ALL",
        incident_type="ALL",
        location={"latitude": 19.0760, "longitude": 72.8777},
        locality={
            "name": "Test",
            "population": 18000,
            "population_density": 8000,
            "affected_population": 500,
        },
        severity=0.7,
        estimated_duration_hours=12,
    )

    service = ResourceRequirementService(RULES_PATH)
    result = service.calculate(incident, urgency=0.5)

    assert len(result.requirements) == 30
    assert len(result.selected_resource_ids) == 30

    for resource_id, qty in result.requirements.items():
        assert qty >= 0, f"{resource_id} has negative quantity"


def test_disaster_specific_hazard_differentiation():
    service = ResourceRequirementService(RULES_PATH)

    flood = Incident(
        incident_id="INC-FLD",
        incident_type="FLOOD",
        location={"latitude": 19.0760, "longitude": 72.8777},
        locality={"name": "Mumbai", "population": 10000, "population_density": 5000, "affected_population": 300},
        severity=0.8,
        estimated_duration_hours=10,
    )
    landslide = Incident(
        incident_id="INC-LND",
        incident_type="LANDSLIDE",
        location={"latitude": 19.0760, "longitude": 72.8777},
        locality={"name": "Mumbai", "population": 10000, "population_density": 5000, "affected_population": 300},
        severity=0.8,
        estimated_duration_hours=10,
    )
    collapse = Incident(
        incident_id="INC-COL",
        incident_type="STRUCTURAL_COLLAPSE",
        location={"latitude": 19.0760, "longitude": 72.8777},
        locality={"name": "Mumbai", "population": 10000, "population_density": 5000, "affected_population": 300},
        severity=0.8,
        estimated_duration_hours=10,
    )

    f_res = service.calculate(flood, urgency=0.8).requirements
    l_res = service.calculate(landslide, urgency=0.8).requirements
    c_res = service.calculate(collapse, urgency=0.8).requirements

    # Flood requires water rescue & water purification, but NOT heavy debris clearance
    assert "boat_water_rescue" in f_res
    assert "water_purification" in f_res
    assert "heavy_machinery_debris_clearance" not in f_res

    # Landslide requires heavy debris clearance, but NOT boat water rescue or water purification
    assert "heavy_machinery_debris_clearance" in l_res
    assert "boat_water_rescue" not in l_res
    assert "water_purification" not in l_res

    # Structural collapse has specialized rescue & debris clearance (10 targeted resources)
    assert "heavy_machinery_debris_clearance" in c_res
    assert "boat_water_rescue" not in c_res
    assert len(c_res) == 10


def test_severity_urgency_increase_quantity():
    incident_low = Incident(
        incident_id="INC-LOW",
        incident_type="FLOOD",
        location={"latitude": 19.0760, "longitude": 72.8777},
        locality={
            "name": "Test",
            "population": 5000,
            "population_density": 8000,
            "affected_population": 100,
        },
        severity=0.0,
        estimated_duration_hours=6,
        selected_resource_ids=["drinking_water"],
    )

    incident_high = Incident(
        incident_id="INC-HIGH",
        incident_type="FLOOD",
        location={"latitude": 19.0760, "longitude": 72.8777},
        locality={
            "name": "Test",
            "population": 5000,
            "population_density": 8000,
            "affected_population": 100,
        },
        severity=1.0,
        estimated_duration_hours=6,
        selected_resource_ids=["drinking_water"],
    )

    service = ResourceRequirementService(RULES_PATH)

    result_low = service.calculate(incident_low, urgency=0.0)
    result_high = service.calculate(incident_high, urgency=1.0)

    assert result_high.requirements["drinking_water"] >= result_low.requirements["drinking_water"]
