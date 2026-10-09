import json
from pathlib import Path

from resource_services.schemas.incident import Incident
from resource_services.schemas.resource_requirement import (
    ResourceRequirement,
    ResourceRequirementResult,
)


class ResourceRequirementService:
    def __init__(self, rules_path: str | Path):
        self.rules_path = Path(rules_path)
        self.rules = self._load_rules()

    def _load_rules(self) -> dict:
        with self.rules_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def calculate(self, incident: Incident) -> ResourceRequirementResult:
        affected_population = incident.locality.affected_population
        resource_rules = self.rules["resources"]

        water = (
            affected_population
            * resource_rules["water"]["base_per_person"]
        )

        food = (
            affected_population
            * resource_rules["food"]["base_per_person"]
        )

        medical_kits = (
            affected_population
            * resource_rules["medical_kits"]["base_per_person"]
        )

        requirements = ResourceRequirement(
            water=water,
            food=food,
            medical_kits=medical_kits,
        )

        return ResourceRequirementResult(
            incident_id=incident.incident_id,
            requirements=requirements,
        )