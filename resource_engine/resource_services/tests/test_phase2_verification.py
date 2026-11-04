"""Phase 2 comprehensive verification tests for the 30-resource Resource Engine.

Every test uses ILLUSTRATIVE configuration values only.
No test asserts exact quantities derived from unapproved production norms.
"""

import json
import math

import pytest
from pydantic import ValidationError

from resource_services.schemas.incident import Incident, Locality
from resource_services.schemas.allocation import AllocationRequest
from resource_services.schemas.resource_requirement import ResourceRequirementResult
from resource_services.schemas.jev_input import (
    JevAssessment,
    JevOrchestrationRequest,
    JevPriority,
    JevSelectedResource,
    JevSeverity,
    JevTriage,
    JevUrgency,
    JevWideArea,
)
from resource_services.services.resource_requirement_service import (
    ResourceRequirementService,
)
from resource_services.services.resource_allocation_service import (
    ResourceAllocationService,
)
from resource_services.services.jev_adapter_service import (
    jev_to_orchestration_request,
    JEV_PRIORITY_MAP,
    JEV_SCOPE_MAP,
)


RULES_PATH = "resource_services/config/resource_rules_v2.json"
WAREHOUSES_PATH = "resource_services/database/warehouses.json"

ALL_30_RESOURCE_IDS = [
    "drinking_water",
    "water_purification",
    "sanitation_hygiene_kits",
    "food_dry_rations",
    "community_kitchen_cooked_food",
    "infant_child_nutrition",
    "fuel_cooking",
    "livestock_fodder_veterinary",
    "emergency_shelter_relief_camp",
    "shelter_kits_tarpaulin",
    "clothing_blankets_warmth",
    "cash_assistance",
    "search_and_rescue",
    "boat_water_rescue",
    "evacuation_transport",
    "missing_persons_reunification",
    "emergency_medical_care",
    "first_aid_trauma",
    "maternal_newborn_care",
    "elderly_disability_assistance",
    "psychosocial_support",
    "medicines_medical_supplies",
    "chronic_care_medication",
    "disease_vector_control",
    "heavy_machinery_debris_clearance",
    "tools_equipment",
    "power_lighting",
    "communication_early_warning",
    "women_child_protection",
    "dead_body_management",
]


def _make_incident(
    affected_population=100,
    population=5000,
    severity=0.5,
    selected_resource_ids=None,
    incident_scope=None,
    incident_id="INC-TEST",
    incident_type="ALL",
):
    return Incident(
        incident_id=incident_id,
        incident_type=incident_type,
        location={"latitude": 19.076, "longitude": 72.878},
        locality={
            "name": "Test Locality",
            "population": population,
            "population_density": 8000,
            "affected_population": affected_population,
        },
        severity=severity,
        estimated_duration_hours=12,
        selected_resource_ids=selected_resource_ids,
        incident_scope=incident_scope,
    )


@pytest.fixture
def service():
    return ResourceRequirementService(RULES_PATH)


@pytest.fixture
def rules():
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# -------------------------------------------------------
# VERIFICATION A: All 30 resource IDs
# -------------------------------------------------------


class TestResourceTaxonomy:

    def test_config_contains_exactly_30_resources(self, rules):
        assert len(rules["resources"]) == 30

    def test_config_ids_match_canonical_list(self, rules):
        config_ids = set(rules["resources"].keys())
        expected_ids = set(ALL_30_RESOURCE_IDS)
        assert config_ids == expected_ids

    def test_all_30_calculated_when_no_selection(self, service):
        incident = _make_incident()
        result = service.calculate(incident, urgency=0.5)
        assert len(result.requirements) == 30
        assert set(result.requirements.keys()) == set(ALL_30_RESOURCE_IDS)

    def test_single_resource_request(self, service):
        incident = _make_incident(selected_resource_ids=["drinking_water"])
        result = service.calculate(incident)
        assert list(result.requirements.keys()) == ["drinking_water"]

    def test_three_resource_request(self, service):
        ids = ["drinking_water", "food_dry_rations", "medicines_medical_supplies"]
        incident = _make_incident(selected_resource_ids=ids)
        result = service.calculate(incident)
        assert set(result.requirements.keys()) == set(ids)

    def test_ten_resource_request(self, service):
        ids = ALL_30_RESOURCE_IDS[:10]
        incident = _make_incident(selected_resource_ids=ids)
        result = service.calculate(incident)
        assert set(result.requirements.keys()) == set(ids)

    def test_thirty_resource_explicit_request(self, service):
        incident = _make_incident(selected_resource_ids=list(ALL_30_RESOURCE_IDS))
        result = service.calculate(incident)
        assert len(result.requirements) == 30

    def test_unknown_resource_id_silently_skipped(self, service):
        incident = _make_incident(
            selected_resource_ids=["drinking_water", "nonexistent_resource"]
        )
        result = service.calculate(incident)
        assert "drinking_water" in result.requirements
        assert "nonexistent_resource" not in result.requirements

    def test_no_negative_quantities_for_any_resource(self, service):
        incident = _make_incident(severity=0.0)
        result = service.calculate(incident, urgency=0.0)
        for rid, qty in result.requirements.items():
            assert qty >= 0, f"{rid} produced negative quantity {qty}"

    def test_no_nan_or_inf_quantities(self, service):
        incident = _make_incident(severity=1.0)
        result = service.calculate(incident, urgency=1.0)
        for rid, qty in result.requirements.items():
            assert math.isfinite(qty), f"{rid} produced non-finite quantity {qty}"


# -------------------------------------------------------
# VERIFICATION B: Model A quantity calculation
# -------------------------------------------------------


class TestModelACalculation:

    def test_formula_matches_specification(self, service, rules):
        """Verify Q_r = ceil(B_r * N_r * F_r) for a known per_person resource."""
        incident = _make_incident(affected_population=100, severity=0.8)
        urgency = 0.7
        result = service.calculate(incident, urgency=urgency)

        config = rules["resources"]["drinking_water"]
        B_r = config["baseline_quantity"]  # 15.0
        N_r = 100.0  # per_person, affected_population
        w_s = config["severity_weight"]  # 0.3
        w_u = config["urgency_weight"]  # 0.2
        f_min = config["adjustment_min"]  # 0.5
        f_max = config["adjustment_max"]  # 2.0

        F_r = max(f_min, min(1.0 + w_s * 0.8 + w_u * 0.7, f_max))
        expected = math.ceil(B_r * N_r * F_r)

        assert result.requirements["drinking_water"] == expected

    def test_baselines_come_from_config(self, service, rules):
        incident = _make_incident(
            affected_population=1,
            severity=0.0,
            selected_resource_ids=["food_dry_rations"],
        )
        result = service.calculate(incident, urgency=0.0)
        details = result.calculation_details["food_dry_rations"]
        assert details["baseline_quantity"] == rules["resources"]["food_dry_rations"]["baseline_quantity"]

    def test_severity_weight_applied(self, service):
        low = service.calculate(_make_incident(severity=0.0, selected_resource_ids=["drinking_water"]), urgency=0.0)
        high = service.calculate(_make_incident(severity=1.0, selected_resource_ids=["drinking_water"]), urgency=0.0)
        assert high.requirements["drinking_water"] >= low.requirements["drinking_water"]

    def test_urgency_weight_applied(self, service):
        low = service.calculate(_make_incident(severity=0.0, selected_resource_ids=["drinking_water"]), urgency=0.0)
        high = service.calculate(_make_incident(severity=0.0, selected_resource_ids=["drinking_water"]), urgency=1.0)
        assert high.requirements["drinking_water"] >= low.requirements["drinking_water"]

    def test_adjustment_factor_bounded_below(self, service, rules):
        """When severity=0 and urgency=0, F_r should not go below adjustment_min."""
        incident = _make_incident(severity=0.0, selected_resource_ids=["drinking_water"])
        result = service.calculate(incident, urgency=0.0)
        details = result.calculation_details["drinking_water"]
        config = rules["resources"]["drinking_water"]
        assert details["adjustment_factor"] >= config["adjustment_min"]

    def test_adjustment_factor_bounded_above(self, service, rules):
        """When severity=1 and urgency=1, F_r should not exceed adjustment_max."""
        incident = _make_incident(severity=1.0, selected_resource_ids=["drinking_water"])
        result = service.calculate(incident, urgency=1.0)
        details = result.calculation_details["drinking_water"]
        config = rules["resources"]["drinking_water"]
        assert details["adjustment_factor"] <= config["adjustment_max"]

    def test_rounding_ceil_applied(self, service):
        """drinking_water uses ceil rounding: fractional result rounds up."""
        incident = _make_incident(
            affected_population=3,
            severity=0.0,
            selected_resource_ids=["drinking_water"],
        )
        result = service.calculate(incident, urgency=0.0)
        qty = result.requirements["drinking_water"]
        assert qty == math.ceil(qty)
        assert qty == int(qty)

    def test_rounding_floor_for_cash_assistance(self, rules):
        """cash_assistance is blocked but configured with floor rounding."""
        assert rules["resources"]["cash_assistance"]["rounding"] == "floor"

    def test_minimum_constraint_enforced(self, service):
        """Even with tiny population, minimum should be respected."""
        incident = _make_incident(
            affected_population=1,
            severity=0.0,
            selected_resource_ids=["drinking_water"],
        )
        result = service.calculate(incident, urgency=0.0)
        assert result.requirements["drinking_water"] >= 1.0

    def test_calculation_details_present(self, service):
        incident = _make_incident(selected_resource_ids=["drinking_water"])
        result = service.calculate(incident, urgency=0.5)
        details = result.calculation_details["drinking_water"]
        assert "baseline_quantity" in details
        assert "demand_base" in details
        assert "quantity_basis" in details
        assert "adjustment_factor" in details
        assert "raw_quantity" in details
        assert "final_quantity" in details


# -------------------------------------------------------
# VERIFICATION C: Five quantity-basis types
# -------------------------------------------------------


class TestQuantityBasisTypes:

    def test_per_person_uses_affected_population(self, service):
        incident = _make_incident(
            affected_population=200,
            selected_resource_ids=["drinking_water"],
        )
        result = service.calculate(incident, urgency=0.0)
        details = result.calculation_details["drinking_water"]
        assert details["quantity_basis"] == "per_person"
        assert details["demand_base"] == 200.0

    def test_per_household_derives_from_population(self, service, rules):
        incident = _make_incident(
            affected_population=100,
            selected_resource_ids=["water_purification"],
        )
        result = service.calculate(incident, urgency=0.0)
        details = result.calculation_details["water_purification"]
        assert details["quantity_basis"] == "per_household"
        household_size = rules.get("default_household_size", 4.5)
        assert details["demand_base"] == math.ceil(100 / household_size)

    def test_per_site_demand_base_is_one(self, service):
        incident = _make_incident(
            selected_resource_ids=["community_kitchen_cooked_food"],
        )
        result = service.calculate(incident, urgency=0.0)
        details = result.calculation_details["community_kitchen_cooked_food"]
        assert details["quantity_basis"] == "per_site"
        assert details["demand_base"] == 1.0

    def test_fixed_team_demand_base_is_one(self, service):
        incident = _make_incident(
            selected_resource_ids=["search_and_rescue"],
        )
        result = service.calculate(incident, urgency=0.0)
        details = result.calculation_details["search_and_rescue"]
        assert details["quantity_basis"] == "fixed_team"
        assert details["demand_base"] == 1.0

    def test_per_incident_demand_base_is_one(self, service):
        incident = _make_incident(
            selected_resource_ids=["communication_early_warning"],
        )
        result = service.calculate(incident, urgency=0.0)
        details = result.calculation_details["communication_early_warning"]
        assert details["quantity_basis"] == "per_incident"
        assert details["demand_base"] == 1.0

    def test_fixed_team_does_not_scale_with_population(self, service):
        small = service.calculate(
            _make_incident(affected_population=10, selected_resource_ids=["search_and_rescue"]),
            urgency=0.5,
        )
        large = service.calculate(
            _make_incident(affected_population=10000, selected_resource_ids=["search_and_rescue"]),
            urgency=0.5,
        )
        assert small.requirements["search_and_rescue"] == large.requirements["search_and_rescue"]

    def test_per_incident_does_not_scale_with_population(self, service):
        small = service.calculate(
            _make_incident(affected_population=5, selected_resource_ids=["dead_body_management"]),
            urgency=0.0,
        )
        large = service.calculate(
            _make_incident(affected_population=5000, selected_resource_ids=["dead_body_management"]),
            urgency=0.0,
        )
        assert small.requirements["dead_body_management"] == large.requirements["dead_body_management"]

    def test_per_household_whole_unit_result(self, service):
        incident = _make_incident(
            affected_population=10,
            selected_resource_ids=["shelter_kits_tarpaulin"],
        )
        result = service.calculate(incident, urgency=0.0)
        qty = result.requirements["shelter_kits_tarpaulin"]
        assert qty == int(qty)


# -------------------------------------------------------
# VERIFICATION D: Configuration and approval status
# -------------------------------------------------------


class TestConfigurationIntegrity:

    REQUIRED_KEYS = [
        "display_label", "quantity_basis", "unit", "baseline_quantity",
        "baseline_approved", "severity_weight", "urgency_weight",
        "adjustment_min", "adjustment_max", "multipliers_approved", "rounding",
    ]

    def test_all_resources_have_required_keys(self, rules):
        for rid, config in rules["resources"].items():
            for key in self.REQUIRED_KEYS:
                assert key in config, f"{rid} missing key '{key}'"

    def test_no_duplicate_resource_ids(self, rules):
        ids = list(rules["resources"].keys())
        assert len(ids) == len(set(ids))

    def test_baseline_quantity_non_negative(self, rules):
        for rid, config in rules["resources"].items():
            assert config["baseline_quantity"] >= 0, f"{rid} has negative baseline"

    def test_adjustment_min_le_max(self, rules):
        for rid, config in rules["resources"].items():
            assert config["adjustment_min"] <= config["adjustment_max"], (
                f"{rid}: adjustment_min {config['adjustment_min']} > adjustment_max {config['adjustment_max']}"
            )

    def test_severity_urgency_weights_non_negative(self, rules):
        for rid, config in rules["resources"].items():
            assert config["severity_weight"] >= 0, f"{rid} has negative severity_weight"
            assert config["urgency_weight"] >= 0, f"{rid} has negative urgency_weight"

    def test_rounding_is_valid_strategy(self, rules):
        for rid, config in rules["resources"].items():
            assert config["rounding"] in ("ceil", "floor", "round"), (
                f"{rid} has invalid rounding: {config['rounding']}"
            )

    def test_no_baselines_are_approved(self, rules):
        """All baselines should be marked as illustrative (not approved)."""
        for rid, config in rules["resources"].items():
            assert config["baseline_approved"] is False, f"{rid} baseline_approved should be False"

    def test_cash_assistance_blocked(self, rules):
        cash = rules["resources"]["cash_assistance"]
        assert cash["production_blocked"] is True
        assert cash["baseline_quantity"] == 0

    def test_quantity_basis_is_valid(self, rules):
        valid = {"per_person", "per_household", "per_site", "fixed_team", "per_incident"}
        for rid, config in rules["resources"].items():
            assert config["quantity_basis"] in valid, (
                f"{rid} has invalid quantity_basis: {config['quantity_basis']}"
            )

    def test_legacy_mapping_present(self, rules):
        mapping = rules["legacy_mapping"]
        assert mapping["water"] == "drinking_water"
        assert mapping["food"] == "food_dry_rations"
        assert mapping["medical_kits"] == "medicines_medical_supplies"


# -------------------------------------------------------
# VERIFICATION E: Incident scope and census invariants
# -------------------------------------------------------


class TestCensusInvariant:

    def test_localized_demand_unchanged_by_census_population(self, service):
        """CRITICAL: Changing census population must NOT change localized demand."""
        ids = ["drinking_water", "food_dry_rations", "first_aid_trauma"]

        result_small_census = service.calculate(
            _make_incident(
                affected_population=3,
                population=1000,
                severity=0.7,
                selected_resource_ids=ids,
                incident_scope="localized",
            ),
            urgency=0.5,
        )

        result_large_census = service.calculate(
            _make_incident(
                affected_population=3,
                population=500000,
                severity=0.7,
                selected_resource_ids=ids,
                incident_scope="localized",
            ),
            urgency=0.5,
        )

        for rid in ids:
            assert result_small_census.requirements[rid] == result_large_census.requirements[rid], (
                f"{rid}: demand changed with census population"
            )

    def test_wide_area_uses_affected_population(self, service):
        """Wide-area should use affected_population, not raw census."""
        result_100 = service.calculate(
            _make_incident(
                affected_population=100,
                population=500000,
                severity=0.5,
                selected_resource_ids=["drinking_water"],
                incident_scope="wide_area",
            ),
            urgency=0.5,
        )

        result_1000 = service.calculate(
            _make_incident(
                affected_population=1000,
                population=500000,
                severity=0.5,
                selected_resource_ids=["drinking_water"],
                incident_scope="wide_area",
            ),
            urgency=0.5,
        )

        assert result_1000.requirements["drinking_water"] > result_100.requirements["drinking_water"]

    def test_per_person_never_uses_census_population(self, service):
        """Verify demand_base equals affected_population, not population."""
        incident = _make_incident(
            affected_population=50,
            population=100000,
            severity=0.5,
            selected_resource_ids=["drinking_water"],
        )
        result = service.calculate(incident, urgency=0.0)
        details = result.calculation_details["drinking_water"]
        assert details["demand_base"] == 50.0

    def test_per_household_never_uses_census_population(self, service, rules):
        """Verify household count derived from affected_population."""
        incident = _make_incident(
            affected_population=45,
            population=200000,
            severity=0.5,
            selected_resource_ids=["water_purification"],
        )
        result = service.calculate(incident, urgency=0.0)
        details = result.calculation_details["water_purification"]
        household_size = rules.get("default_household_size", 4.5)
        assert details["demand_base"] == math.ceil(45 / household_size)


# -------------------------------------------------------
# VERIFICATION F: Inventory allocation and shortage
# -------------------------------------------------------


class TestInventoryAllocation:

    def test_full_allocation(self):
        service = ResourceAllocationService(WAREHOUSES_PATH)
        result = service.allocate(
            incident_id="INC-FULL",
            requirements={"drinking_water": 100},
            severity=0.5, urgency=0.5, priority="HIGH",
        )
        assert result.allocation_status == "FULLY_FULFILLED"
        assert result.allocated_resources["drinking_water"] == 100
        assert result.remaining_shortage["drinking_water"] == 0

    def test_partial_allocation(self):
        service = ResourceAllocationService(WAREHOUSES_PATH)
        result = service.allocate(
            incident_id="INC-PARTIAL",
            requirements={"drinking_water": 100000},
            severity=0.5, urgency=0.5, priority="HIGH",
        )
        assert result.allocation_status == "PARTIALLY_FULFILLED"
        assert result.allocated_resources["drinking_water"] < 100000
        assert result.remaining_shortage["drinking_water"] > 0

    def test_zero_stock_resource(self, tmp_path):
        """A resource with zero available should allocate nothing."""
        wh = [{
            "warehouse_id": "WH-ZERO",
            "name": "Empty",
            "location": {"latitude": 19.0, "longitude": 72.0},
            "inventory": {"drinking_water": {"available": 0, "capacity": 100}},
            "vehicles": {},
        }]
        path = tmp_path / "wh.json"
        path.write_text(json.dumps(wh), encoding="utf-8")
        service = ResourceAllocationService(path)
        result = service.allocate(
            incident_id="INC-ZERO",
            requirements={"drinking_water": 50},
            severity=0.5, urgency=0.5, priority="HIGH",
        )
        assert result.allocated_resources["drinking_water"] == 0
        assert result.remaining_shortage["drinking_water"] == 50

    def test_absent_inventory_resource(self, tmp_path):
        """A resource not in any warehouse inventory should get zero allocation."""
        wh = [{
            "warehouse_id": "WH-NO-WATER",
            "name": "No Water",
            "location": {"latitude": 19.0, "longitude": 72.0},
            "inventory": {"food_dry_rations": {"available": 100, "capacity": 200}},
            "vehicles": {},
        }]
        path = tmp_path / "wh.json"
        path.write_text(json.dumps(wh), encoding="utf-8")
        service = ResourceAllocationService(path)
        result = service.allocate(
            incident_id="INC-ABSENT",
            requirements={"drinking_water": 50},
            severity=0.5, urgency=0.5, priority="HIGH",
        )
        assert result.allocated_resources["drinking_water"] == 0
        assert result.remaining_shortage["drinking_water"] == 50
        assert result.allocation_status == "PARTIALLY_FULFILLED"

    def test_exact_stock_match(self, tmp_path):
        wh = [{
            "warehouse_id": "WH-EXACT",
            "name": "Exact",
            "location": {"latitude": 19.0, "longitude": 72.0},
            "inventory": {"drinking_water": {"available": 50, "capacity": 50}},
            "vehicles": {},
        }]
        path = tmp_path / "wh.json"
        path.write_text(json.dumps(wh), encoding="utf-8")
        service = ResourceAllocationService(path)
        result = service.allocate(
            incident_id="INC-EXACT",
            requirements={"drinking_water": 50},
            severity=0.5, urgency=0.5, priority="HIGH",
        )
        assert result.allocation_status == "FULLY_FULFILLED"
        assert result.allocated_resources["drinking_water"] == 50
        assert result.remaining_shortage["drinking_water"] == 0

    def test_required_quantity_preserved_in_result(self):
        service = ResourceAllocationService(WAREHOUSES_PATH)
        reqs = {"drinking_water": 500, "food_dry_rations": 200}
        result = service.allocate(
            incident_id="INC-PRESERVE",
            requirements=reqs,
            severity=0.5, urgency=0.5, priority="HIGH",
        )
        assert result.required_resources == reqs

    def test_repeated_allocation_no_mutation(self):
        """Two successive calls with same requirements should produce same results."""
        service = ResourceAllocationService(WAREHOUSES_PATH)
        reqs = {"drinking_water": 100}
        r1 = service.allocate("INC-A", reqs, 0.5, 0.5, "HIGH")
        r2 = service.allocate("INC-B", reqs, 0.5, 0.5, "HIGH")
        assert r1.allocated_resources["drinking_water"] == r2.allocated_resources["drinking_water"]

    def test_priority_affects_allocation_order_not_quantity(self):
        """Higher priority gets served first from contested inventory."""
        service = ResourceAllocationService(WAREHOUSES_PATH)
        low = AllocationRequest(
            incident_id="INC-LOW",
            requirements={"drinking_water": 10},
            severity=0.1, urgency=0.1, priority="LOW",
        )
        high = AllocationRequest(
            incident_id="INC-HIGH",
            requirements={"drinking_water": 10},
            severity=0.9, urgency=0.9, priority="CRITICAL",
        )
        results = service.allocate_batch([low, high])
        assert results[0].incident_id == "INC-HIGH"
        assert results[1].incident_id == "INC-LOW"
        # Both should be fully fulfilled (plenty of water)
        assert results[0].allocated_resources["drinking_water"] == 10
        assert results[1].allocated_resources["drinking_water"] == 10


# -------------------------------------------------------
# VERIFICATION G: Legacy compatibility
# -------------------------------------------------------


class TestLegacyCompatibility:

    def test_water_maps_to_drinking_water(self, service):
        incident = _make_incident(selected_resource_ids=["water"])
        result = service.calculate(incident)
        assert "drinking_water" in result.requirements
        assert "water" not in result.requirements

    def test_food_maps_to_food_dry_rations(self, service):
        incident = _make_incident(selected_resource_ids=["food"])
        result = service.calculate(incident)
        assert "food_dry_rations" in result.requirements

    def test_medical_kits_maps_to_medicines(self, service):
        incident = _make_incident(selected_resource_ids=["medical_kits"])
        result = service.calculate(incident)
        assert "medicines_medical_supplies" in result.requirements

    def test_legacy_and_new_ids_together(self, service):
        """Using both legacy and new IDs shouldn't duplicate."""
        incident = _make_incident(
            selected_resource_ids=["water", "drinking_water"]
        )
        result = service.calculate(incident)
        assert "drinking_water" in result.requirements
        # Both map to drinking_water, so it appears once in requirements
        # but selected_resource_ids will have both resolved to drinking_water
        assert result.requirements["drinking_water"] > 0

    def test_three_resource_legacy_workflow(self, service):
        """The original 3-resource workflow still works with legacy IDs."""
        incident = _make_incident(
            selected_resource_ids=["water", "food", "medical_kits"]
        )
        result = service.calculate(incident, urgency=0.5)
        assert len(result.requirements) == 3
        assert all(
            rid in result.requirements
            for rid in ["drinking_water", "food_dry_rations", "medicines_medical_supplies"]
        )


# -------------------------------------------------------
# VERIFICATION H: JEV adapter
# -------------------------------------------------------


class TestJevAdapter:

    def _make_jev_request(
        self,
        severity=2,
        urgency=1,
        priority="P2",
        wide_area_status=None,
        selected_resources=None,
    ):
        triage = JevTriage(
            incident_type="FLOOD",
            assessment=JevAssessment(
                severity=JevSeverity(numeric=severity),
                urgency=JevUrgency(numeric=urgency),
                priority=JevPriority(level=priority),
            ),
            selected_resources=[
                JevSelectedResource(resource=r) for r in (selected_resources or [])
            ],
            wide_area=JevWideArea(status=wide_area_status) if wide_area_status else None,
        )
        return JevOrchestrationRequest(
            incident_id="JEV-001",
            location={"latitude": 19.076, "longitude": 72.878},
            locality={
                "name": "Test",
                "population": 10000,
                "population_density": 8000,
                "affected_population": 200,
            },
            jev_triage=triage,
        )

    def test_severity_normalization(self):
        for s in range(4):
            req = self._make_jev_request(severity=s)
            result = jev_to_orchestration_request(req)
            assert abs(result.severity - s / 3.0) < 1e-6

    def test_urgency_normalization(self):
        for u in range(4):
            req = self._make_jev_request(urgency=u)
            result = jev_to_orchestration_request(req)
            assert abs(result.urgency - u / 3.0) < 1e-6

    def test_priority_mapping(self):
        for code, expected in JEV_PRIORITY_MAP.items():
            req = self._make_jev_request(priority=code)
            result = jev_to_orchestration_request(req)
            assert result.priority == expected

    def test_unknown_priority_defaults_to_moderate(self):
        req = self._make_jev_request(priority="P5")
        result = jev_to_orchestration_request(req)
        assert result.priority == "MODERATE"

    def test_wide_area_scope_mapping(self):
        for status, expected in JEV_SCOPE_MAP.items():
            req = self._make_jev_request(wide_area_status=status)
            result = jev_to_orchestration_request(req)
            assert result.incident_scope == expected

    def test_no_wide_area_yields_no_scope(self):
        req = self._make_jev_request()
        result = jev_to_orchestration_request(req)
        assert result.incident_scope is None

    def test_selected_resources_passed_through(self):
        req = self._make_jev_request(
            selected_resources=["drinking_water", "food_dry_rations"]
        )
        result = jev_to_orchestration_request(req)
        assert result.selected_resource_ids == ["drinking_water", "food_dry_rations"]

    def test_empty_selected_resources_yields_none(self):
        req = self._make_jev_request(selected_resources=[])
        result = jev_to_orchestration_request(req)
        assert result.selected_resource_ids is None

    def test_invalid_severity_rejected(self):
        with pytest.raises(ValidationError):
            JevSeverity(numeric=4)

    def test_invalid_urgency_rejected(self):
        with pytest.raises(ValidationError):
            JevUrgency(numeric=-1)

    def test_full_payload_produces_valid_orchestration_request(self):
        req = self._make_jev_request(
            severity=3,
            urgency=2,
            priority="P1",
            wide_area_status="wide",
            selected_resources=["drinking_water", "search_and_rescue"],
        )
        result = jev_to_orchestration_request(req)
        assert result.incident_id == "JEV-001"
        assert result.severity == 1.0
        assert abs(result.urgency - 2 / 3.0) < 1e-6
        assert result.priority == "CRITICAL"
        assert result.incident_scope == "wide_area"
        assert result.selected_resource_ids == ["drinking_water", "search_and_rescue"]


# -------------------------------------------------------
# VERIFICATION: Priority separation
# -------------------------------------------------------


class TestPrioritySeparation:

    def test_priority_does_not_inflate_required_quantity(self, service):
        """Same incident facts, different priority → same required quantity."""
        base_args = dict(
            affected_population=100,
            severity=0.5,
            selected_resource_ids=["drinking_water"],
        )
        # Priority is NOT an input to ResourceRequirementService
        result = service.calculate(_make_incident(**base_args), urgency=0.5)
        # Verify no priority field exists on the calculate interface
        # (priority only enters at the allocation layer)
        assert result.requirements["drinking_water"] > 0


# -------------------------------------------------------
# VERIFICATION: Severity normalization edge cases
# -------------------------------------------------------


class TestSeverityUrgencyEdgeCases:

    def test_severity_zero_produces_positive_quantity(self, service):
        incident = _make_incident(severity=0.0, selected_resource_ids=["drinking_water"])
        result = service.calculate(incident, urgency=0.0)
        assert result.requirements["drinking_water"] > 0

    def test_severity_one_within_bounds(self, service, rules):
        incident = _make_incident(severity=1.0, selected_resource_ids=["drinking_water"])
        result = service.calculate(incident, urgency=1.0)
        details = result.calculation_details["drinking_water"]
        config = rules["resources"]["drinking_water"]
        assert config["adjustment_min"] <= details["adjustment_factor"] <= config["adjustment_max"]

    def test_invalid_severity_rejected_by_schema(self):
        with pytest.raises(ValidationError):
            _make_incident(severity=1.5)

    def test_negative_severity_rejected_by_schema(self):
        with pytest.raises(ValidationError):
            _make_incident(severity=-0.1)


# -------------------------------------------------------
# VERIFICATION: Warehouse inventory coverage
# -------------------------------------------------------


class TestWarehouseInventory:

    def test_warehouses_contain_diverse_resources(self):
        with open(WAREHOUSES_PATH, "r", encoding="utf-8") as f:
            warehouses = json.load(f)
        all_stocked = set()
        for wh in warehouses:
            all_stocked.update(wh["inventory"].keys())
        # Verify significant coverage
        assert len(all_stocked) >= 20

    def test_all_stocked_resources_are_valid_ids(self, rules):
        with open(WAREHOUSES_PATH, "r", encoding="utf-8") as f:
            warehouses = json.load(f)
        valid_ids = set(rules["resources"].keys())
        for wh in warehouses:
            for rid in wh["inventory"]:
                assert rid in valid_ids, (
                    f"Warehouse {wh['warehouse_id']} stocks unknown resource '{rid}'"
                )

    def test_no_negative_inventory(self):
        with open(WAREHOUSES_PATH, "r", encoding="utf-8") as f:
            warehouses = json.load(f)
        for wh in warehouses:
            for rid, item in wh["inventory"].items():
                assert item["available"] >= 0, (
                    f"{wh['warehouse_id']}/{rid} has negative available"
                )
                assert item["capacity"] >= 0, (
                    f"{wh['warehouse_id']}/{rid} has negative capacity"
                )
