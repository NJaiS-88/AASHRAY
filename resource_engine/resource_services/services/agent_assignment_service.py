import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from resource_services.schemas.agent_assignment import (
    AgentAssignmentRequest,
    AgentAssignmentResult,
    Responder,
)
from resource_services.schemas.mission_lifecycle import (
    MissionAssignment,
    MissionRecord,
)
from resource_services.services.mission_store import (
    MissionStateError,
    MissionStore,
    default_missions_path,
)


EARTH_RADIUS_KM = 6371.0


def haversine_km(
    latitude1: float,
    longitude1: float,
    latitude2: float,
    longitude2: float,
) -> float:
    # Great-circle (straight-line) distance. Used only to compare responder
    # proximity; it is not a road or route distance.

    phi1 = math.radians(latitude1)
    phi2 = math.radians(latitude2)

    delta_phi = math.radians(latitude2 - latitude1)
    delta_lambda = math.radians(longitude2 - longitude1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )

    # Clamp guards against a slightly-above-1 value from rounding.
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(a, 1.0)))


class NoResponderAvailableError(Exception):
    error_code = "NO_RESPONDER_AVAILABLE"

    def __init__(self, required_responder_types: list[str]):
        self.required_responder_types = list(required_responder_types)

        super().__init__(
            "No AVAILABLE responder of type "
            f"{self.required_responder_types} was found."
        )


class ResponderStatusError(Exception):
    # A responder status change could not be applied or persisted.
    pass


class AgentAssignmentService:
    def __init__(
        self,
        responders_path: str | Path,
        missions_path: str | Path | None = None,
    ):
        self.responders_path = Path(responders_path)
        self.mission_store = MissionStore(
            missions_path or default_missions_path(self.responders_path)
        )
        self.responders = self._load_responders()

    def _load_responders(self) -> list[Responder]:
        with self.responders_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, list):
            raise ValueError(
                f"{self.responders_path} must contain a list of responders."
            )

        responders = []

        for index, record in enumerate(data):
            try:
                responders.append(Responder.model_validate(record))
            except ValidationError as error:
                raise ValueError(
                    f"Invalid responder record at index {index} in "
                    f"{self.responders_path}: {error}"
                ) from error

        responder_ids = [responder.responder_id for responder in responders]

        if len(set(responder_ids)) != len(responder_ids):
            raise ValueError(
                f"Duplicate responder_id found in {self.responders_path}."
            )

        return responders

    def assign(
        self,
        request: AgentAssignmentRequest,
    ) -> AgentAssignmentResult:

        # COMPLETED and CANCELLED are final. A responder assigned to such a
        # mission would stay BUSY with nothing left to release it.
        mission = self.mission_store.get(request.mission_id)

        if mission is not None and mission.status != "ASSIGNED":
            raise MissionStateError(
                "MISSION_ALREADY_CLOSED",
                f"Mission {request.mission_id} is {mission.status}; no "
                "responder can be assigned to it.",
            )

        # Select from the persisted state so a responder made BUSY by an
        # earlier assignment is never selected again.
        self.responders = self._load_responders()

        required_types = set(request.required_responder_types)

        eligible = [
            responder
            for responder in self.responders
            if responder.status == "AVAILABLE"
            and responder.vehicle_type in required_types
        ]

        if not eligible:
            raise NoResponderAvailableError(request.required_responder_types)

        target = request.first_warehouse_location

        distances = [
            (
                responder,
                haversine_km(
                    responder.location.latitude,
                    responder.location.longitude,
                    target.latitude,
                    target.longitude,
                ),
            )
            for responder in eligible
        ]

        # min() returns the first of several equal distances, so exact ties
        # are resolved by the order of responders.json.
        selected, distance = min(
            distances,
            key=lambda item: item[1],
        )

        # The assignment is only reported once BUSY has been persisted.
        self._update_status(
            selected.responder_id,
            from_status="AVAILABLE",
            to_status="BUSY",
        )

        assignment_id = f"ASSIGN-{uuid4().hex[:8].upper()}"

        # ...and once the mission records which responder is BUSY for it.
        self._record_assignment(
            request.mission_id,
            assignment_id,
            selected.responder_id,
        )

        return AgentAssignmentResult(
            assignment_id=assignment_id,
            mission_id=request.mission_id,
            responder_id=selected.responder_id,
            responder_type=selected.vehicle_type,
            responder_location=selected.location,
            target_warehouse_id=request.first_warehouse_id,
            target_warehouse_location=target,
            distance_to_warehouse_km=round(distance, 3),
            assignment_status="ASSIGNED",
        )

    def release_responder(self, responder_id: str) -> Responder:
        # BUSY -> AVAILABLE. Called by MissionLifecycleService when the
        # responder's mission is completed or cancelled.
        return self._update_status(
            responder_id,
            from_status="BUSY",
            to_status="AVAILABLE",
        )

    def _record_assignment(
        self,
        mission_id: str,
        assignment_id: str,
        responder_id: str,
    ) -> None:

        assignment = MissionAssignment(
            assignment_id=assignment_id,
            responder_id=responder_id,
            assigned_at=datetime.now(timezone.utc),
        )

        try:
            mission = self.mission_store.get(mission_id)

            if mission is None:
                mission = MissionRecord(
                    mission_id=mission_id,
                    status="ASSIGNED",
                    assignments=[assignment],
                )
            else:
                mission.assignments.append(assignment)

            self.mission_store.save(mission)

        except Exception as error:
            # Without the record nothing could ever release the responder,
            # so undo BUSY and report no assignment.
            try:
                self._update_status(
                    responder_id,
                    from_status="BUSY",
                    to_status="AVAILABLE",
                )
            except ResponderStatusError as rollback_error:
                raise ResponderStatusError(
                    f"Could not record responder {responder_id} for mission "
                    f"{mission_id}: {error}. Returning {responder_id} to "
                    f"AVAILABLE also failed: {rollback_error}"
                ) from error

            raise ResponderStatusError(
                f"Could not record responder {responder_id} for mission "
                f"{mission_id}: {error}. {responder_id} was returned to "
                "AVAILABLE."
            ) from error

    def _update_status(
        self,
        responder_id: str,
        from_status: str,
        to_status: str,
    ) -> Responder:

        # Re-read the file so the change is applied to the persisted state,
        # not to a possibly stale in-memory copy.
        try:
            with self.responders_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, ValueError) as error:
            raise ResponderStatusError(
                f"Could not read {self.responders_path}: {error}"
            ) from error

        if not isinstance(data, list):
            raise ResponderStatusError(
                f"{self.responders_path} must contain a list of responders."
            )

        record = next(
            (
                item
                for item in data
                if isinstance(item, dict)
                and item.get("responder_id") == responder_id
            ),
            None,
        )

        if record is None:
            raise ResponderStatusError(
                f"Responder {responder_id} not found in "
                f"{self.responders_path}."
            )

        if record.get("status") != from_status:
            raise ResponderStatusError(
                f"Responder {responder_id} is {record.get('status')}, "
                f"expected {from_status}."
            )

        # Only the status changes. Location and every other field are kept.
        record["status"] = to_status

        # Write to a temporary file first so a failed write can never leave
        # a truncated responders.json behind.
        temporary_path = self.responders_path.with_name(
            self.responders_path.name + ".tmp"
        )

        try:
            temporary_path.write_text(
                json.dumps(data, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_path, self.responders_path)
        except OSError as error:
            temporary_path.unlink(missing_ok=True)
            raise ResponderStatusError(
                f"Could not save responder {responder_id} as {to_status}: "
                f"{error}"
            ) from error

        self.responders = self._load_responders()

        return Responder.model_validate(record)
