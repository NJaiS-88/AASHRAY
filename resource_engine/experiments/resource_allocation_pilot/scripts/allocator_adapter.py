"""Adapter between the pilot scenarios and the EXISTING AASHRAY allocator.

The existing allocator is imported and used unchanged:

    resource_services.services.resource_allocation_service
        .ResourceAllocationService.allocate_batch

How order control works without modifying the allocator
-------------------------------------------------------
``allocate_batch`` ranks requests by its own internal score before
allocating, using a stable sort. The adapter gives every request the SAME
placeholder severity / urgency / priority (config:
``existing_allocator.placeholder_inputs``). All internal scores are then
equal, the stable sort keeps the input order, and the allocator processes
emergencies in exactly the order the experiment presents. This is verified
on every call: if the allocator ever returns results in a different order,
``AllocationOrderError`` is raised instead of silently continuing.

What the allocator receives per emergency
-----------------------------------------
Only ``incident_id`` (the emergency id) and ``requirements`` carry scenario
information. The real S, U, P_GT and ground-truth labels are never passed.
The placeholders only feed the allocator's cosmetic output fields
(normalized_priority / overall_priority_score / final_priority_level), which
this adapter discards.

Inventory
---------
The allocator loads warehouses from a JSON file. The adapter writes each
scenario's inventory (already in the existing ``Warehouse`` schema) to a
temporary file outside the repository and constructs a fresh service from
it. ``allocate_batch`` builds a fresh shared working inventory on every
call, so every order condition starts from the same stock.
"""

import json
from pathlib import Path

from pilot_common import ensure_repo_on_path

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
    def __init__(
        self,
        scenario: dict,
        placeholder_inputs: dict,
        work_dir: Path,
    ):
        self.scenario_id = scenario["scenario_id"]
        self.placeholder_inputs = placeholder_inputs

        warehouses_path = Path(work_dir) / "warehouses.json"
        warehouses_path.write_text(
            json.dumps(scenario["resource_inventory"]),
            encoding="utf-8",
        )

        self.service = ResourceAllocationService(warehouses_path)

        # Only the demand of each emergency is kept for the allocator.
        self.requirements = {
            emergency["emergency_id"]: emergency["resource_requirements"]
            for emergency in scenario["emergencies"]
        }

        self.calls_order_verified = 0

    def allocate_in_order(self, ordered_ids: list[str]) -> list[dict]:

        if sorted(ordered_ids) != sorted(self.requirements):
            raise ValueError(
                f"{self.scenario_id}: order must contain every emergency "
                f"exactly once."
            )

        requests = [
            AllocationRequest(
                incident_id=emergency_id,
                requirements=ResourceRequirement(
                    **self.requirements[emergency_id]
                ),
                severity=self.placeholder_inputs["severity"],
                urgency=self.placeholder_inputs["urgency"],
                priority=self.placeholder_inputs["priority"],
            )
            for emergency_id in ordered_ids
        ]

        results = self.service.allocate_batch(requests)

        processed_ids = [result.incident_id for result in results]

        if processed_ids != list(ordered_ids):
            raise AllocationOrderError(
                f"{self.scenario_id}: existing allocator processed "
                f"{processed_ids} but the experiment presented "
                f"{list(ordered_ids)}."
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
                "allocation_status": result.allocation_status,
            }
            for result in results
        ]
