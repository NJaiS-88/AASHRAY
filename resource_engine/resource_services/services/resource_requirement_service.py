import json
import math
from pathlib import Path

from resource_services.schemas.incident import Incident
from resource_services.schemas.resource_requirement import ResourceRequirementResult


class ResourceRequirementService:
    def __init__(self, rules_path: str | Path):
        self.rules_path = Path(rules_path)
        self.rules = self._load_rules()

    def _load_rules(self) -> dict:
        with self.rules_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _resolve_legacy_id(self, resource_id: str) -> str:
        legacy_map = self.rules.get("legacy_mapping", {})
        return legacy_map.get(resource_id, resource_id)

    def _get_demand_base(
        self,
        quantity_basis: str,
        affected_population: int,
        default_household_size: float,
    ) -> float:
        if quantity_basis == "per_person":
            return float(affected_population)
        if quantity_basis == "per_household":
            return math.ceil(affected_population / default_household_size)
        if quantity_basis in ("per_site", "fixed_team", "per_incident"):
            return 1.0
        return float(affected_population)

    def _matches_incident_type(
        self,
        incident_type: str | None,
        applicability: list[str],
    ) -> bool:
        if not incident_type:
            return True
        norm = incident_type.lower().strip().replace(" ", "_").replace("-", "_")
        if norm in applicability:
            return True
        aliases = {
            "structural_collapse": ["building_collapse"],
            "collapse": ["building_collapse"],
            "building_or_structure_collapse": ["building_collapse"],
            "flooding_waterlogging": ["urban_flood", "flood"],
            "urban_flooding": ["urban_flood", "flood"],
            "waterlogging": ["urban_flood", "flood"],
            "inundation": ["flood", "urban_flood"],
            "avalanche": ["snow_avalanche"],
            "wildfire": ["fire"],
            "forest_fire": ["fire"],
            "fire_or_explosion": ["fire"],
            "road_or_transport_incident": ["road_incident"],
            "road_accident": ["road_incident"],
            "traffic_accident": ["road_incident"],
            "storm_or_cyclone_damage": ["cyclone"],
            "cyclone_storm": ["cyclone"],
            "medical_emergency": ["road_incident", "building_collapse"],
            "all": list(applicability),
            "general_disaster": list(applicability),
        }
        for alias in aliases.get(norm, []):
            if alias in applicability:
                return True
        return False

    def calculate(
        self,
        incident: Incident,
        urgency: float = 0.0,
    ) -> ResourceRequirementResult:
        """Model A: Q_r = ceil(B_r * N_r * F_r)"""
        resource_configs = self.rules["resources"]
        default_household_size = self.rules.get("default_household_size", 4.5)
        affected_population = incident.locality.affected_population

        selected_ids = incident.selected_resource_ids
        if selected_ids:
            selected_ids = [self._resolve_legacy_id(rid) for rid in selected_ids]
        else:
            inc_type = getattr(incident, "incident_type", None)
            selected_ids = [
                rid
                for rid, cfg in resource_configs.items()
                if self._matches_incident_type(inc_type, cfg.get("applicability", []))
            ]
            if not selected_ids:
                selected_ids = list(resource_configs.keys())

        severity = incident.severity

        requirements: dict[str, float] = {}
        calculation_details: dict[str, dict] = {}

        for resource_id in selected_ids:
            config = resource_configs.get(resource_id)
            if config is None:
                continue

            if config.get("production_blocked", False):
                requirements[resource_id] = 0.0
                calculation_details[resource_id] = {
                    "blocked": True,
                    "reason": config.get("baseline_source", "Blocked"),
                }
                continue

            B_r = config.get("baseline_quantity", config.get("base_per_person", 1.0))
            if B_r <= 0:
                requirements[resource_id] = 0.0
                calculation_details[resource_id] = {"baseline_zero": True}
                continue

            N_r = self._get_demand_base(
                config.get("quantity_basis", "per_person"),
                affected_population,
                default_household_size,
            )

            w_s = config.get("severity_weight", 0.0)
            w_u = config.get("urgency_weight", 0.0)
            f_min = config.get("adjustment_min", 0.5)
            f_max = config.get("adjustment_max", 2.0)

            F_r = 1.0 + w_s * severity + w_u * urgency
            F_r = max(f_min, min(F_r, f_max))

            raw = B_r * N_r * F_r

            rounding = config.get("rounding", "ceil")
            if rounding == "ceil":
                quantity = math.ceil(raw)
            elif rounding == "floor":
                quantity = math.floor(raw)
            else:
                quantity = round(raw)

            minimum = config.get("minimum")
            maximum = config.get("maximum")
            if minimum is not None:
                quantity = max(quantity, minimum)
            if maximum is not None:
                quantity = min(quantity, maximum)

            requirements[resource_id] = float(quantity)
            calculation_details[resource_id] = {
                "baseline_quantity": B_r,
                "demand_base": N_r,
                "quantity_basis": config.get("quantity_basis", "per_person"),
                "adjustment_factor": round(F_r, 4),
                "raw_quantity": round(raw, 4),
                "final_quantity": float(quantity),
            }

        return ResourceRequirementResult(
            incident_id=incident.incident_id,
            requirements=requirements,
            selected_resource_ids=selected_ids,
            calculation_details=calculation_details,
        )
