import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from resource_services.schemas.mission_lifecycle import (
    MissionLifecycleResult,
    MissionRecord,
)
from resource_services.services.agent_assignment_service import (
    AgentAssignmentService,
)
from resource_services.services.mission_store import (
    MissionStateError,
    MissionStore,
    default_missions_path,
)


logger = logging.getLogger(__name__)


class MissionLifecycleService:
    # Closes a mission (ASSIGNED -> COMPLETED | CANCELLED) and releases the
    # responders recorded for it (BUSY -> AVAILABLE, location kept).
    #
    # Which responders to release comes only from the mission's own record
    # in missions.json, never from which responders happen to be BUSY.

    def __init__(
        self,
        responders_path: str | Path,
        missions_path: str | Path | None = None,
    ):
        self.responders_path = Path(responders_path)
        self.mission_store = MissionStore(
            missions_path or default_missions_path(self.responders_path)
        )

    def complete(self, mission_id: str) -> MissionLifecycleResult:
        return self._close(mission_id, "COMPLETED")

    def cancel(self, mission_id: str) -> MissionLifecycleResult:
        return self._close(mission_id, "CANCELLED")

    def _close(
        self,
        mission_id: str,
        final_status: Literal["COMPLETED", "CANCELLED"],
    ) -> MissionLifecycleResult:

        mission = self.mission_store.get(mission_id)

        # CREATED missions are not persisted: no record means no responder
        # was ever assigned, so there is nothing to release.
        if mission is None:
            raise MissionStateError(
                "MISSION_NOT_ASSIGNED",
                f"No responder assignment is recorded for mission "
                f"{mission_id}; no responder was released.",
            )

        responder_ids = list(
            dict.fromkeys(item.responder_id for item in mission.assignments)
        )

        # Idempotent: closing again the same way changes nothing. Its
        # responders are not touched again; one may already be BUSY for
        # another mission.
        if mission.status == final_status:
            return MissionLifecycleResult(
                mission_id=mission_id,
                status=final_status,
                previous_status=mission.status,
                responder_ids=responder_ids,
            )

        if mission.status != "ASSIGNED":
            raise MissionStateError(
                "MISSION_ALREADY_CLOSED",
                f"Mission {mission_id} is {mission.status}; it cannot be "
                f"{final_status}.",
            )

        assignment_service = AgentAssignmentService(
            self.responders_path,
            self.mission_store.path,
        )

        current_status = {
            responder.responder_id: responder.status
            for responder in assignment_service.responders
        }

        released = []

        for responder_id in responder_ids:
            other_mission = self._other_active_mission(responder_id, mission)

            if other_mission is not None:
                # Only possible if the responder was released outside the
                # lifecycle and re-assigned: it now serves the other mission.
                logger.warning(
                    "Mission %s: responder %s not released, it is assigned "
                    "to active mission %s",
                    mission_id,
                    responder_id,
                    other_mission,
                )
                continue

            if current_status.get(responder_id) != "BUSY":
                logger.warning(
                    "Mission %s: responder %s not released, it is %s",
                    mission_id,
                    responder_id,
                    current_status.get(responder_id, "missing"),
                )
                continue

            # Compare-and-set BUSY -> AVAILABLE; only status is written.
            released.append(assignment_service.release_responder(responder_id))

        # Close only after the release. If this save fails, the mission stays
        # ASSIGNED and a retry is safe: released responders are no longer
        # BUSY, or are BUSY for another active mission, and are skipped.
        previous_status = mission.status
        mission.status = final_status
        mission.closed_at = datetime.now(timezone.utc)

        self.mission_store.save(mission)

        return MissionLifecycleResult(
            mission_id=mission_id,
            status=final_status,
            previous_status=previous_status,
            responder_ids=responder_ids,
            released_responders=released,
        )

    def _other_active_mission(
        self,
        responder_id: str,
        mission: MissionRecord,
    ) -> str | None:

        return next(
            (
                other.mission_id
                for other in self.mission_store.load()
                if other.mission_id != mission.mission_id
                and other.status == "ASSIGNED"
                and any(
                    item.responder_id == responder_id
                    for item in other.assignments
                )
            ),
            None,
        )
