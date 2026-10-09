from typing import Literal

from pydantic import BaseModel, Field

from resource_services.schemas.common import Location


ResponderVehicleType = Literal[
    "RESCUE_TRUCK",
    "AMBULANCE",
    "FIRE_TRUCK",
]


class Responder(BaseModel):
    # One record of database/responders.json.

    responder_id: str

    name: str

    vehicle_type: ResponderVehicleType

    location: Location

    status: Literal[
        "AVAILABLE",
        "BUSY",
    ]


class AgentAssignmentRequest(BaseModel):
    mission_id: str

    # Any one of these types may execute the mission.
    required_responder_types: list[ResponderVehicleType] = Field(
        min_length=1,
    )

    # Selection target: the mission's first pickup, not its destination.
    first_warehouse_location: Location

    first_warehouse_id: str | None = None


class AgentAssignmentResult(BaseModel):
    assignment_id: str
    mission_id: str

    responder_id: str

    responder_type: ResponderVehicleType

    responder_location: Location

    target_warehouse_id: str | None = None

    target_warehouse_location: Location

    # Straight-line (Haversine) distance, not a road distance.
    distance_to_warehouse_km: float

    assignment_status: Literal["ASSIGNED"]
