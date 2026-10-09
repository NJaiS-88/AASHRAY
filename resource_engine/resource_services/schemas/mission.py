from typing import Literal

from pydantic import BaseModel, Field, model_validator

from resource_services.schemas.allocation import PriorityLevel
from resource_services.schemas.common import Location


class WarehousePickup(BaseModel):
    warehouse_id: str
    location: Location
    supplies: dict[str, float]


class RouteLeg(BaseModel):
    leg_index: int

    # The missionId this leg was sent to the Route Engine with
    # ("<mission_id>-LEG-<leg_index>"); its MissionRouteState key.
    # Optional for unplanned legs; required on every leg of an AVAILABLE
    # route (see RouteData).
    route_engine_mission_id: str | None = None

    source_type: Literal[
        "RESPONDER",
        "WAREHOUSE",
    ]

    source_id: str

    destination_type: Literal[
        "WAREHOUSE",
        "DESTINATION",
    ]

    destination_id: str

    source_location: Location

    destination_location: Location

    distance_km: float

    estimated_time_minutes: float

    coordinates: list[Location] = Field(default_factory=list)

    encoded_polyline: str | None = None

    route_id: str | None = None

    score: float | None = None

    road_condition_status: str | None = None

    road_condition_confidence: str | None = None

    matched_incidents: list[dict] = Field(default_factory=list)

    reasons: list[str] = Field(default_factory=list)


class RouteData(BaseModel):
    status: Literal[
        "NOT_AVAILABLE",
        "AVAILABLE",
    ]

    coordinates: list[Location] = Field(default_factory=list)

    distance_km: float | None = None

    estimated_time_minutes: float | None = None

    legs: list[RouteLeg] = Field(default_factory=list)

    @model_validator(mode="after")
    def routed_legs_have_route_engine_ids(self):
        # Every leg of a planned route was planned by the Route Engine, so it
        # must say under which Route Engine missionId.
        if self.status == "AVAILABLE":
            missing = [
                leg.leg_index
                for leg in self.legs
                if not leg.route_engine_mission_id
            ]

            if missing:
                raise ValueError(
                    "AVAILABLE route has legs without a "
                    f"route_engine_mission_id: leg_index {missing}"
                )

        return self


class MissionCreationRequest(BaseModel):
    incident_id: str

    destination: Location

    risk_score: float = Field(
        ge=0.0,
        le=1.0,
    )

    # Same levels as Resource Allocation's final_priority_level.
    priority: PriorityLevel | None = None

    patient_present: bool

    # The actually allocated resources, not the required resources.
    resources: dict[str, float]

    warehouse_pickups: list[WarehousePickup]


class PickupSequenceItem(BaseModel):
    sequence: int

    type: Literal[
        "WAREHOUSE",
        "DESTINATION",
    ]

    warehouse_id: str | None = None

    supplies: dict[str, float] | None = None


class MissionCreationResult(BaseModel):
    mission_id: str
    incident_id: str

    destination: Location

    required_responder_types: list[str]

    risk_score: float

    priority: PriorityLevel | None = None

    resources: dict[str, float]

    pickup_sequence: list[PickupSequenceItem]

    route: RouteData

    status: Literal["CREATED"]