from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from resource_services.schemas.agent_assignment import Responder


# Mission lifecycle:
#
#   CREATED  -> ASSIGNED    Agent Assignment made a responder BUSY for it
#   ASSIGNED -> COMPLETED   its responders are released (BUSY -> AVAILABLE)
#   ASSIGNED -> CANCELLED   its responders are released (BUSY -> AVAILABLE)
#
# CREATED is what Mission Creation returns; it has no side effects, so a
# mission is only persisted (database/missions.json) once a responder has
# been assigned to it. COMPLETED and CANCELLED are final.
MissionStatus = Literal[
    "CREATED",
    "ASSIGNED",
    "COMPLETED",
    "CANCELLED",
]


class MissionAssignment(BaseModel):
    # One successful Agent Assignment for the mission.
    assignment_id: str

    responder_id: str

    assigned_at: datetime


class MissionRecord(BaseModel):
    # One record of database/missions.json: which responders are BUSY for
    # this mission, so completion/cancellation releases exactly those.
    mission_id: str

    status: Literal[
        "ASSIGNED",
        "COMPLETED",
        "CANCELLED",
    ]

    # Normally one. /agent/assign may be called again for the same mission,
    # and every responder it assigns is recorded here.
    assignments: list[MissionAssignment] = Field(min_length=1)

    # When the mission became COMPLETED or CANCELLED.
    closed_at: datetime | None = None


class MissionLifecycleResult(BaseModel):
    mission_id: str

    # The mission status after the operation.
    status: Literal[
        "COMPLETED",
        "CANCELLED",
    ]

    # Equal to `status` when the mission was already closed this way and
    # the call changed nothing.
    previous_status: Literal[
        "ASSIGNED",
        "COMPLETED",
        "CANCELLED",
    ]

    # Every responder recorded as assigned to this mission.
    responder_ids: list[str]

    # Responders this call changed BUSY -> AVAILABLE, as persisted (location
    # unchanged). Empty when nothing was released.
    released_responders: list[Responder] = Field(default_factory=list)
