import json
import os
from pathlib import Path

from pydantic import ValidationError

from resource_services.schemas.mission_lifecycle import MissionRecord


MISSIONS_FILE_NAME = "missions.json"


def default_missions_path(responders_path: str | Path) -> Path:
    # Mission records live next to the responders they refer to
    # (database/missions.json beside database/responders.json), so any
    # service given a responders file uses the matching missions file.
    return Path(responders_path).with_name(MISSIONS_FILE_NAME)


class MissionStateError(Exception):
    # A valid request that the mission's lifecycle state does not allow.
    # Nothing is changed when it is raised.

    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        super().__init__(message)


class MissionStore:
    # Persists MissionRecords in a JSON list, like responders.json.
    # A missing file means no mission has been assigned yet.

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> list[MissionRecord]:
        if not self.path.exists():
            return []

        with self.path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, list):
            raise ValueError(f"{self.path} must contain a list of missions.")

        records = []

        for index, item in enumerate(data):
            try:
                records.append(MissionRecord.model_validate(item))
            except ValidationError as error:
                raise ValueError(
                    f"Invalid mission record at index {index} in "
                    f"{self.path}: {error}"
                ) from error

        mission_ids = [record.mission_id for record in records]

        if len(set(mission_ids)) != len(mission_ids):
            raise ValueError(f"Duplicate mission_id found in {self.path}.")

        return records

    def get(self, mission_id: str) -> MissionRecord | None:
        return next(
            (
                record
                for record in self.load()
                if record.mission_id == mission_id
            ),
            None,
        )

    def save(self, record: MissionRecord) -> None:
        # Insert or replace the record, keeping the order of the others.
        records = self.load()

        for index, existing in enumerate(records):
            if existing.mission_id == record.mission_id:
                records[index] = record
                break
        else:
            records.append(record)

        # Same as responders.json: write a temporary file, then replace, so
        # a failed write never leaves a truncated missions.json.
        temporary_path = self.path.with_name(self.path.name + ".tmp")

        try:
            temporary_path.write_text(
                json.dumps(
                    [item.model_dump(mode="json") for item in records],
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_path, self.path)
        except OSError:
            temporary_path.unlink(missing_ok=True)
            raise
