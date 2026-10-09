"""Shared paths, configuration, validated-code imports and helpers.

The validated FCFS / AASHRAY implementation (development policies.py) and
MILP implementation (milp_model.py, analytical_optimum.py) are imported
read-only from their own folders. Bytecode writing is disabled so nothing
is written into those folders.

Dry runs: AASHRAY_FINAL_ROOT and AASHRAY_FINAL_CONFIG redirect the data /
results folders and the config to a scratch location. The official run uses
neither.
"""

import sys

sys.dont_write_bytecode = True

import csv  # noqa: E402
import gzip  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import platform  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402


FINAL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = FINAL_ROOT.parents[1]
EXPERIMENTS = REPO_ROOT / "experiments"

PILOT_ROOT = EXPERIMENTS / "resource_allocation_pilot"
DEVELOPMENT_ROOT = EXPERIMENTS / "resource_allocation_development"
MILP_ROOT = EXPERIMENTS / "resource_allocation_milp"

DEVELOPMENT_CONFIG_PATH = DEVELOPMENT_ROOT / "config" / "development_config.json"
DEVELOPMENT_DATASET_PATH = DEVELOPMENT_ROOT / "data" / "development_3000_scenarios.json"
PILOT_DATASET_PATH = PILOT_ROOT / "data" / "pilot_500_scenarios.json"
FROZEN_PARAMETERS_PATH = DEVELOPMENT_ROOT / "results" / "frozen_parameters.json"
MILP_CONFIG_PATH = MILP_ROOT / "config" / "milp_config.json"

OFFICIAL_CONFIG_PATH = FINAL_ROOT / "config" / "final_config.json"

OUTPUT_ROOT = Path(os.environ.get("AASHRAY_FINAL_ROOT", FINAL_ROOT))
CONFIG_PATH = Path(os.environ.get("AASHRAY_FINAL_CONFIG", OFFICIAL_CONFIG_PATH))
OFFICIAL = OUTPUT_ROOT == FINAL_ROOT and CONFIG_PATH == OFFICIAL_CONFIG_PATH

DATA_DIR = OUTPUT_ROOT / "data"
RESULTS_DIR = OUTPUT_ROOT / "results"

DATASET_PATH = DATA_DIR / "final_12000_scenarios.json"
PREFLIGHT_PATH = RESULTS_DIR / "preflight.json"
PROTECTED_MANIFEST_PATH = RESULTS_DIR / "protected_manifest.json"
GENERATOR_EQUIVALENCE_PATH = RESULTS_DIR / "generator_equivalence.json"
FREEZE_PATH = RESULTS_DIR / "dataset_freeze.json"
RUN_METADATA_PATH = RESULTS_DIR / "run_metadata.json"
SCENARIO_RESULTS_PATH = RESULTS_DIR / "final_scenario_results.csv"
POLICY_ALLOCATIONS_PATH = RESULTS_DIR / "final_policy_allocations.csv.gz"
MILP_ALLOCATIONS_PATH = RESULTS_DIR / "final_milp_allocations.csv.gz"
GATE_PATH = RESULTS_DIR / "gate_report.json"
METHOD_SUMMARY_PATH = RESULTS_DIR / "final_method_summary.csv"
SCARCITY_SUMMARY_PATH = RESULTS_DIR / "final_scarcity_summary.csv"
WIN_TIE_LOSS_PATH = RESULTS_DIR / "final_win_tie_loss.csv"
STATISTICAL_TESTS_PATH = RESULTS_DIR / "final_statistical_tests.json"
SUMMARY_PATH = RESULTS_DIR / "final_summary.json"
VALIDATION_PATH = RESULTS_DIR / "validation_report.json"
ENVIRONMENT_PATH = RESULTS_DIR / "environment.json"
FILE_MANIFEST_PATH = RESULTS_DIR / "file_hash_manifest.json"

RESOURCE_TYPES = ("water", "food", "medical_kits")
SCARCITY_LEVELS = ("LOW", "MODERATE", "HIGH")
OFFICIAL_SCENARIO_COUNT = 12000

EXCLUDED_PARTS = {".git", "node_modules", "__pycache__", ".pytest_cache"}

# Validated implementations, imported read-only.
for _path in (DEVELOPMENT_ROOT / "scripts", MILP_ROOT / "scripts", REPO_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_frozen_parameters() -> dict:
    frozen = json.loads(FROZEN_PARAMETERS_PATH.read_text(encoding="utf-8"))
    return {key: frozen[key] for key in ("config_id", "alpha", "k", "m", "n")}


def milp_options() -> dict:
    return json.loads(MILP_CONFIG_PATH.read_text(encoding="utf-8"))["solver"]["options"]


def derive_seed(*parts) -> int:
    # Identical to the development derive_seed (sha256 -> 63-bit int).
    text = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") >> 1


def gt_clauses(severity: float, urgency: float) -> dict:
    # The frozen development GT rule, unchanged.
    return {
        "both_high": severity >= 0.8 and urgency >= 0.8,
        "severity_extreme": severity >= 0.95,
        "urgency_extreme": urgency >= 0.95,
    }


def ground_truth_critical(severity: float, urgency: float) -> int:
    return 1 if any(gt_clauses(severity, urgency).values()) else 0


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_text(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, allow_nan=True) + "\n"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def format_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return "NaN" if math.isnan(value) else repr(value)
    return str(value)


def csv_text(rows: list[dict], fields: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(fields)
    for row in rows:
        writer.writerow([format_value(row[field]) for field in fields])
    return buffer.getvalue()


def write_gzip_csv(path: Path, header: list[str], rows) -> None:
    # mtime=0 so the file is byte-reproducible.
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as raw:
        with gzip.GzipFile(filename=path.name[:-3], fileobj=raw, mode="wb", mtime=0) as packed:
            with io.TextIOWrapper(packed, encoding="utf-8", newline="\n") as text:
                writer = csv.writer(text, lineterminator="\n")
                writer.writerow(header)
                for row in rows:
                    writer.writerow([format_value(v) for v in row])


def read_gzip_csv(path: Path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        yield from csv.DictReader(file)


def read_csv(path: Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def parse_float(text: str) -> float:
    return math.nan if text in ("", "NaN") else float(text)


def parse_bool(text: str) -> bool:
    return text == "true"


def scenario_fingerprint(scenario: dict) -> str:
    # Content hash of everything the methods consume.
    content = {
        "emergencies": [
            [e["emergency_id"], e["severity"], e["urgency"], e["arrival_timestamp"],
             e["ground_truth_critical"], [e["resource_requirements"][r] for r in RESOURCE_TYPES]]
            for e in scenario["emergencies"]
        ],
        "inventory": [
            [w["warehouse_id"], [w["inventory"][r]["available"] for r in RESOURCE_TYPES]]
            for w in scenario["resource_inventory"]
        ],
    }
    return sha256_text(json.dumps(content, separators=(",", ":")))


def content_fingerprint(scenario: dict) -> str:
    # Identifier-free content (for duplicate / cross-dataset checks).
    content = sorted(
        (e["severity"], e["urgency"], e["arrival_offset_seconds"],
         tuple(e["resource_requirements"][r] for r in RESOURCE_TYPES))
        for e in scenario["emergencies"]
    )
    supply = [w["inventory"][r]["available"] for w in scenario["resource_inventory"]
              for r in RESOURCE_TYPES]
    return sha256_text(json.dumps([content, supply], separators=(",", ":")))


def protected_manifest() -> dict:
    """sha256 of every repository file outside the final experiment, grouped."""

    groups = {"application": {}, "pilot": {}, "development": {}, "milp": {}}

    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(REPO_ROOT)
        if EXCLUDED_PARTS.intersection(relative.parts):
            continue
        parts = relative.parts
        if parts[:2] == ("experiments", FINAL_ROOT.name):
            continue
        if parts[:2] == ("experiments", PILOT_ROOT.name):
            group = "pilot"
        elif parts[:2] == ("experiments", DEVELOPMENT_ROOT.name):
            group = "development"
        elif parts[:2] == ("experiments", MILP_ROOT.name):
            group = "milp"
        else:
            group = "application"
        groups[group][relative.as_posix()] = sha256_file(path)

    return groups


def final_code_hashes() -> dict:
    # Config and scripts of the final experiment (pre-registration record).
    hashes = {CONFIG_PATH.name: sha256_file(CONFIG_PATH)}
    for path in sorted((FINAL_ROOT / "scripts").glob("*.py")):
        hashes[f"scripts/{path.name}"] = sha256_file(path)
    return hashes


def git_state() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    try:
        status = run("status", "--porcelain")
        return {"commit": run("rev-parse", "HEAD"),
                "working_tree_has_uncommitted_or_untracked_files": bool(status),
                "status_porcelain": status.splitlines()}
    except (OSError, subprocess.CalledProcessError) as error:
        return {"commit": None, "error": str(error)}


def environment_info() -> dict:
    import numpy
    import scipy

    try:
        from scipy.optimize._highspy import _core
        highs = f"{_core.HIGHS_VERSION_MAJOR}.{_core.HIGHS_VERSION_MINOR}.{_core.HIGHS_VERSION_PATCH}"
    except Exception:
        highs = None

    cpu = platform.processor()
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            cpu = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            pass

    try:
        import psutil
        ram = psutil.virtual_memory().total
        cores = psutil.cpu_count(logical=False)
    except ImportError:
        ram, cores = None, None

    try:
        import pydantic
        pydantic_version = pydantic.VERSION
    except ImportError:
        pydantic_version = None

    return {
        "cpu": cpu,
        "physical_cores": cores,
        "logical_cpus": os.cpu_count(),
        "ram_bytes": ram,
        "ram_gib": round(ram / 2**30, 2) if ram else None,
        "os": platform.platform(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "numpy_version": numpy.__version__,
        "scipy_version": scipy.__version__,
        "highs_version": highs,
        "pydantic_version": pydantic_version,
        "solver": "HiGHS via scipy.optimize.milp",
        "timer": "time.perf_counter",
    }
