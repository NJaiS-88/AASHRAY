"""Shared paths, configuration, seed derivation and the fixed GT rule.

No module in this experiment touches global random state: every random
stream is a ``random.Random`` seeded through ``derive_seed``.
"""

import hashlib
import json
import sys
from pathlib import Path


DEV_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DEV_ROOT.parents[1]
PILOT_ROOT = REPO_ROOT / "experiments" / "resource_allocation_pilot"

CONFIG_PATH = DEV_ROOT / "config" / "development_config.json"
DATASET_PATH = DEV_ROOT / "data" / "development_3000_scenarios.json"
RESULTS_DIR = DEV_ROOT / "results"

GRID_PATH = RESULTS_DIR / "candidate_grid.csv"
CONFIGURATION_RESULTS_PATH = RESULTS_DIR / "configuration_results.csv"
TOP_10_PATH = RESULTS_DIR / "top_10_configurations.csv"
EQUIVALENCE_PATH = RESULTS_DIR / "ranking_equivalence.csv"
BASELINE_PATH = RESULTS_DIR / "baseline_comparison.csv"
SCARCITY_PATH = RESULTS_DIR / "scarcity_analysis.csv"
PER_SCENARIO_PATH = RESULTS_DIR / "per_scenario_results.csv.gz"
SUMMARY_PATH = RESULTS_DIR / "development_summary.json"
MANIFEST_PATH = RESULTS_DIR / "application_manifest.json"
VALIDATION_PATH = RESULTS_DIR / "validation_report.json"
FROZEN_PATH = RESULTS_DIR / "frozen_parameters.json"

# The development set has a fixed size. The generator refuses any other
# size, so this code can never produce the separate final test set.
DEVELOPMENT_SCENARIO_COUNT = 3000

BOTH_HIGH_THRESHOLD = 0.8
SINGLE_EXTREME_THRESHOLD = 0.95


def ensure_repo_on_path() -> None:
    # The application imports itself as ``resource_services.*``.
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def load_config(path: Path = CONFIG_PATH) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def derive_seed(*parts) -> int:
    # sha256 -> 63-bit int; stable across processes, unlike hash().
    text = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") >> 1


def gt_clauses(severity: float, urgency: float) -> dict:
    # The fixed development GT rule. Never depends on alpha, k, m, n.
    return {
        "both_high": (
            severity >= BOTH_HIGH_THRESHOLD and urgency >= BOTH_HIGH_THRESHOLD
        ),
        "severity_extreme": severity >= SINGLE_EXTREME_THRESHOLD,
        "urgency_extreme": urgency >= SINGLE_EXTREME_THRESHOLD,
    }


def ground_truth_critical(severity: float, urgency: float) -> int:
    return 1 if any(gt_clauses(severity, urgency).values()) else 0


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_text(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


EXCLUDED_PARTS = {".git", "node_modules", "__pycache__", ".pytest_cache"}


def application_manifest() -> dict[str, str]:
    # sha256 of every repository file outside this development experiment
    # (application code, data, config and the pilot experiment).
    manifest = {}

    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file():
            continue

        relative = path.relative_to(REPO_ROOT)

        if EXCLUDED_PARTS.intersection(relative.parts):
            continue

        if relative.parts[:2] == ("experiments", DEV_ROOT.name):
            continue

        manifest[relative.as_posix()] = sha256_file(path)

    return manifest
