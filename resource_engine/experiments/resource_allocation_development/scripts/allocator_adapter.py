"""Adapter to the EXISTING AASHRAY allocator (used unchanged).

Same mechanism as the pilot. ``allocate_batch`` ranks requests by its own
score with a stable sort. Every request gets the SAME placeholder
severity/urgency/priority, so those scores tie and the allocator processes
emergencies in exactly the order presented. This is checked on every call;
a violation raises ``AllocationOrderError``.

The allocator only ever receives an emergency id and its demand. S, U,
GT labels and AASHRAY parameters are never passed to it. The placeholder
values only feed its cosmetic priority output fields, which are discarded.
"""

import json
from pathlib import Path

from dev_common import ensure_repo_on_path

ensure_repo_on_path()

from resource_services.schemas.allocation import AllocationRequest  # noqa: E402
from resource_services.schemas.resource_requirement import (  # noqa: E402
    ResourceRequirement,
)
from resource_services.services.resource_allocation_service import (  # noqa: E402
    ResourceAllocationService,
)


RESOURCE_FIELDS = ("water", "food", "medical_kits")


class AllocationOrderError(RuntimeError):
    pass


class ExistingAllocatorAdapter:
    def __init__(self, scenario: dict, placeholder_inputs: dict, work_dir: Path):
        self.scenario_id = scenario["scenario_id"]
        self.placeholder_inputs = placeholder_inputs

        warehouses_path = Path(work_dir) / "warehouses.json"
        warehouses_path.write_text(
            json.dumps(scenario["resource_inventory"]),
            encoding="utf-8",
        )

        self.service = ResourceAllocationService(warehouses_path)

        self.requirements = {
            emergency["emergency_id"]: emergency["resource_requirements"]
            for emergency in scenario["emergencies"]
        }

        self.calls_order_verified = 0

    def allocate_in_order(self, ordered_ids) -> list[dict]:

        ordered_ids = list(ordered_ids)

        if sorted(ordered_ids) != sorted(self.requirements):
            raise ValueError(
                f"{self.scenario_id}: order must contain every emergency once."
            )

        requests = [
            AllocationRequest(
                incident_id=emergency_id,
                requirements=ResourceRequirement(**self.requirements[emergency_id]),
                severity=self.placeholder_inputs["severity"],
                urgency=self.placeholder_inputs["urgency"],
                priority=self.placeholder_inputs["priority"],
            )
            for emergency_id in ordered_ids
        ]

        results = self.service.allocate_batch(requests)

        processed_ids = [result.incident_id for result in results]

        if processed_ids != ordered_ids:
            raise AllocationOrderError(
                f"{self.scenario_id}: allocator processed {processed_ids}, "
                f"experiment presented {ordered_ids}."
            )

        self.calls_order_verified += 1

        return [
            {
                "emergency_id": result.incident_id,
                "required": {
                    field: getattr(result.required_resources, field)
                    for field in RESOURCE_FIELDS
                },
                "allocated": {
                    field: getattr(result.allocated_resources, field)
                    for field in RESOURCE_FIELDS
                },
                "shortage": {
                    field: getattr(result.remaining_shortage, field)
                    for field in RESOURCE_FIELDS
                },
            }
            for result in results
        ]
