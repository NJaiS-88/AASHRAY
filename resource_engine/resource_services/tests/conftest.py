import shutil
from pathlib import Path

import pytest


DATABASE_DIR = Path("resource_services/database")

RESPONDERS_PATH = DATABASE_DIR / "responders.json"

# Real dummy database files that tests must never leave modified.
GUARDED_DATABASE_FILES = [
    RESPONDERS_PATH,
    DATABASE_DIR / "warehouses.json",
    DATABASE_DIR / "missions.json",
]


@pytest.fixture(scope="session", autouse=True)
def guard_dummy_database():
    # Agent Assignment writes responder status. Tests must use temporary
    # copies; if any test still touches the real files, restore them and
    # report it.
    snapshots = {path: path.read_bytes() for path in GUARDED_DATABASE_FILES}

    yield

    modified = []

    for path, content in snapshots.items():
        if path.read_bytes() != content:
            path.write_bytes(content)
            modified.append(str(path))

    if modified:
        pytest.fail(
            f"Tests modified the real dummy database (restored): {modified}"
        )


@pytest.fixture
def responders_copy(tmp_path) -> Path:
    # A temporary copy of the real responders.json, safe to mutate.
    copy_path = tmp_path / "real_responders_copy.json"
    shutil.copyfile(RESPONDERS_PATH, copy_path)
    return copy_path
