"""Shared paths, configuration and protected-file manifests."""

import hashlib
import json
from pathlib import Path


MILP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MILP_ROOT.parents[1]

DEVELOPMENT_ROOT = REPO_ROOT / "experiments" / "resource_allocation_development"
PILOT_ROOT = REPO_ROOT / "experiments" / "resource_allocation_pilot"

DEVELOPMENT_DATASET_PATH = DEVELOPMENT_ROOT / "data" / "development_3000_scenarios.json"
FROZEN_PARAMETERS_PATH = DEVELOPMENT_ROOT / "results" / "frozen_parameters.json"

CONFIG_PATH = MILP_ROOT / "config" / "milp_config.json"
RESULTS_DIR = MILP_ROOT / "results"

HAND_CHECK_PATH = RESULTS_DIR / "hand_check_results.json"
RESULTS_CSV_PATH = RESULTS_DIR / "development_milp_results.csv"
ALLOCATIONS_PATH = RESULTS_DIR / "development_milp_allocations.csv.gz"
SUMMARY_PATH = RESULTS_DIR / "development_milp_summary.json"
ENVIRONMENT_PATH = RESULTS_DIR / "solver_environment.json"
VALIDATION_PATH = RESULTS_DIR / "validation_report.json"
MANIFEST_PATH = RESULTS_DIR / "protected_manifest.json"

RESOURCE_TYPES = ("water", "food", "medical_kits")

DEVELOPMENT_SCENARIO_COUNT = 3000

EXCLUDED_PARTS = {".git", "node_modules", "__pycache__", ".pytest_cache"}


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def json_text(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, allow_nan=True) + "\n"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def protected_manifest() -> dict[str, dict[str, str]]:
    """sha256 of every repository file outside this MILP experiment, grouped
    into application files, the pilot and the development experiment."""

    groups = {"application": {}, "pilot": {}, "development": {}}

    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file():
            continue

        relative = path.relative_to(REPO_ROOT)

        if EXCLUDED_PARTS.intersection(relative.parts):
            continue

        parts = relative.parts

        if parts[:2] == ("experiments", MILP_ROOT.name):
            continue

        if parts[:2] == ("experiments", PILOT_ROOT.name):
            group = "pilot"
        elif parts[:2] == ("experiments", DEVELOPMENT_ROOT.name):
            group = "development"
        else:
            group = "application"

        groups[group][relative.as_posix()] = sha256_file(path)

    return groups
