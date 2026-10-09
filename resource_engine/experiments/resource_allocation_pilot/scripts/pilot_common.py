"""Shared paths, configuration loading and deterministic seed derivation.

Nothing in this module touches global random state. Every random stream in
the pilot is a ``random.Random`` instance seeded through ``derive_seed``.
"""

import hashlib
import json
import sys
from pathlib import Path


PILOT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PILOT_ROOT.parents[1]

CONFIG_PATH = PILOT_ROOT / "config" / "pilot_config.json"
DATASET_PATH = PILOT_ROOT / "data" / "pilot_500_scenarios.json"
RESULTS_DIR = PILOT_ROOT / "results"

PILOT_RESULTS_PATH = RESULTS_DIR / "pilot_results.csv"
ORDER_SENSITIVITY_PATH = RESULTS_DIR / "order_sensitivity.csv"
SUMMARY_PATH = RESULTS_DIR / "pilot_summary.json"
VALIDATION_PATH = RESULTS_DIR / "validation_report.json"

# The pilot dataset size is fixed. The generator refuses any other size so
# this experiment can never be used to produce the separate final test set.
PILOT_SCENARIO_COUNT = 500

GT_THRESHOLD = 0.8
GT_DECIMALS = 6


def ensure_repo_on_path() -> None:
    # The existing application imports itself as ``resource_services.*``,
    # which requires the repository root on sys.path. Adding it here avoids
    # touching any existing application file.
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def load_config(path: Path = CONFIG_PATH) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def derive_seed(*parts) -> int:
    # sha256 of the joined parts -> 63-bit int. Stable across processes and
    # platforms, unlike Python's salted hash().
    text = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") >> 1


def ground_truth_score(severity: float, urgency: float) -> float:
    # Fixed reference score. Never depends on alpha, k, m or n.
    return round(0.5 * severity + 0.5 * urgency, GT_DECIMALS)


def ground_truth_critical(reference_score: float) -> int:
    return 1 if reference_score > GT_THRESHOLD else 0


def dump_json(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_text(data), encoding="utf-8")


def json_text(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
