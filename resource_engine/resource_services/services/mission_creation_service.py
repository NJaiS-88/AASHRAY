from uuid import uuid4

from resource_services.schemas.mission import (
    MissionCreationRequest,
    MissionCreationResult,
    PickupSequenceItem,
    RouteData,
)


class MissionCreationService:

    def create_mission(
        self,
        request: MissionCreationRequest,
    ) -> MissionCreationResult:

        responder_types = self._determine_responder_type(
            priority=request.priority,
            resources=request.resources,
            patient_present=request.patient_present,
        )

        pickup_sequence = self._create_pickup_sequence(
            warehouse_pickups=request.warehouse_pickups,
        )

        mission_id = f"MIS-{uuid4().hex[:8].upper()}"

        return MissionCreationResult(
            mission_id=mission_id,
            incident_id=request.incident_id,
            destination=request.destination,
            required_responder_types=responder_types,
            risk_score=request.risk_score,
            priority=request.priority,
            resources=request.resources,
            pickup_sequence=pickup_sequence,
            route=RouteData(
                status="NOT_AVAILABLE",
            ),
            status="CREATED",
        )

    def _determine_responder_type(
        self,
        priority: str,
        resources: dict[str, float],
        patient_present: bool,
    ) -> list[str]:

        # Temporary rule.
        # Final responder selection will later consider
        # flood depth, road condition, and route safety.

        if patient_present:
            return ["AMBULANCE"]

        if priority in ["HIGH", "CRITICAL"]:
            return ["RESCUE_TRUCK"]

        total_resources = sum(resources.values())

        if total_resources > 1000:
            return ["RESCUE_TRUCK"]

        return ["RESCUE_TRUCK"]

    def _create_pickup_sequence(
        self,
        warehouse_pickups,
    ) -> list[PickupSequenceItem]:

        pickup_sequence = []

        sequence_number = 1

        for warehouse in warehouse_pickups:

            pickup_sequence.append(
                PickupSequenceItem(
                    sequence=sequence_number,
                    type="WAREHOUSE",
                    warehouse_id=warehouse.warehouse_id,
                    supplies=warehouse.supplies,
                )
            )

            sequence_number += 1

        pickup_sequence.append(
            PickupSequenceItem(
                sequence=sequence_number,
                type="DESTINATION",
            )
        )

        return pickup_sequence