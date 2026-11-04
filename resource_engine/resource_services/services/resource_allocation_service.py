import json
from pathlib import Path
from uuid import uuid4

from resource_services.schemas.warehouse import Warehouse
from resource_services.schemas.allocation import (
    AllocationRequest,
    AllocationResult,
    WarehouseAllocation,
)


PRIORITY_NORMALIZATION = {
    "LOW": 0.25,
    "MODERATE": 0.50,
    "HIGH": 0.75,
    "CRITICAL": 1.00,
}

DEFAULT_PRIORITY_WEIGHTS = {
    "severity": 0.4,
    "urgency": 0.4,
    "priority": 0.2,
}

PRIORITY_LEVEL_THRESHOLDS = [
    (0.35, "LOW"),
    (0.60, "MODERATE"),
    (0.80, "HIGH"),
]

SCORE_PRECISION = 4


class ResourceAllocationService:
    def __init__(
        self,
        warehouses_path: str | Path,
        priority_rules_path: str | Path | None = None,
    ):
        self.warehouses_path = Path(warehouses_path)
        self.warehouses = self._load_warehouses()

        self.priority_rules_path = (
            Path(priority_rules_path)
            if priority_rules_path is not None
            else None
        )
        self.priority_weights = self._load_priority_weights()

    def _load_warehouses(self) -> list[Warehouse]:
        with self.warehouses_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return [Warehouse(**warehouse) for warehouse in data]

    def _load_priority_weights(self) -> dict[str, float]:
        if self.priority_rules_path is None:
            return dict(DEFAULT_PRIORITY_WEIGHTS)

        with self.priority_rules_path.open("r", encoding="utf-8") as file:
            rules = json.load(file)

        weights = rules.get("allocation_priority", {}).get("weights")

        if not weights:
            return dict(DEFAULT_PRIORITY_WEIGHTS)

        return {
            key: float(weights.get(key, default))
            for key, default in DEFAULT_PRIORITY_WEIGHTS.items()
        }

    def normalize_priority(self, priority: str) -> float:
        return PRIORITY_NORMALIZATION[priority]

    def calculate_overall_priority_score(
        self,
        severity: float,
        urgency: float,
        normalized_priority: float,
    ) -> float:

        score = (
            self.priority_weights["severity"] * severity
            + self.priority_weights["urgency"] * urgency
            + self.priority_weights["priority"] * normalized_priority
        )

        return round(score, SCORE_PRECISION)

    def determine_priority_level(self, overall_priority_score: float) -> str:

        score = round(overall_priority_score, SCORE_PRECISION)

        for threshold, level in PRIORITY_LEVEL_THRESHOLDS:
            if score <= threshold:
                return level

        return "CRITICAL"

    def _build_working_inventory(self) -> dict[str, dict[str, float]]:

        return {
            warehouse.warehouse_id: {
                resource: item.available
                for resource, item in warehouse.inventory.items()
            }
            for warehouse in self.warehouses
        }

    def allocate(
        self,
        incident_id: str,
        requirements: dict[str, float],
        severity: float,
        urgency: float,
        priority: str,
    ) -> AllocationResult:

        return self._allocate_from_inventory(
            incident_id=incident_id,
            requirements=requirements,
            severity=severity,
            urgency=urgency,
            priority=priority,
            working_inventory=self._build_working_inventory(),
        )

    def allocate_batch(
        self,
        requests: list[AllocationRequest],
    ) -> list[AllocationResult]:

        ranked_requests = sorted(
            requests,
            key=lambda request: self.calculate_overall_priority_score(
                severity=request.severity,
                urgency=request.urgency,
                normalized_priority=self.normalize_priority(request.priority),
            ),
            reverse=True,
        )

        working_inventory = self._build_working_inventory()

        results = []

        for request in ranked_requests:

            results.append(
                self._allocate_from_inventory(
                    incident_id=request.incident_id,
                    requirements=request.requirements,
                    severity=request.severity,
                    urgency=request.urgency,
                    priority=request.priority,
                    working_inventory=working_inventory,
                )
            )

        return results

    def _allocate_from_inventory(
        self,
        incident_id: str,
        requirements: dict[str, float],
        severity: float,
        urgency: float,
        priority: str,
        working_inventory: dict[str, dict[str, float]],
    ) -> AllocationResult:

        normalized_priority = self.normalize_priority(priority)

        overall_priority_score = self.calculate_overall_priority_score(
            severity=severity,
            urgency=urgency,
            normalized_priority=normalized_priority,
        )

        final_priority_level = self.determine_priority_level(
            overall_priority_score
        )

        remaining = dict(requirements)
        allocated = {resource: 0.0 for resource in requirements}

        warehouse_allocations = []

        for warehouse in self.warehouses:

            warehouse_stock = working_inventory[warehouse.warehouse_id]

            warehouse_supplies: dict[str, float] = {}

            for resource, needed in remaining.items():
                if needed <= 0:
                    continue

                available = warehouse_stock.get(resource, 0.0)
                quantity = min(available, needed)

                if quantity > 0:
                    warehouse_supplies[resource] = quantity
                    allocated[resource] += quantity
                    remaining[resource] -= quantity
                    warehouse_stock[resource] = available - quantity

            if warehouse_supplies:
                warehouse_allocations.append(
                    WarehouseAllocation(
                        warehouse_id=warehouse.warehouse_id,
                        supplies=warehouse_supplies,
                    )
                )

            if all(qty <= 0 for qty in remaining.values()):
                break

        shortage = {
            resource: max(qty, 0.0)
            for resource, qty in remaining.items()
        }

        if all(qty <= 0 for qty in shortage.values()):
            status = "FULLY_FULFILLED"
        else:
            status = "PARTIALLY_FULFILLED"

        return AllocationResult(
            allocation_id=f"ALLOC-{uuid4().hex[:8].upper()}",
            incident_id=incident_id,
            required_resources=requirements,
            warehouse_allocations=warehouse_allocations,
            allocated_resources=allocated,
            remaining_shortage=shortage,
            allocation_status=status,
            normalized_priority=normalized_priority,
            overall_priority_score=overall_priority_score,
            final_priority_level=final_priority_level,
        )
