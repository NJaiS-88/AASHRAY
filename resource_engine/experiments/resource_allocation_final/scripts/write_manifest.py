"""Write environment.json and file_hash_manifest.json (run last).

Usage (from the repository root, after validate_final.py):

    python experiments/resource_allocation_final/scripts/write_manifest.py
"""

from datetime import datetime, timezone

from final_common import (
    CONFIG_PATH,
    DATASET_PATH,
    ENVIRONMENT_PATH,
    FILE_MANIFEST_PATH,
    FINAL_ROOT,
    FROZEN_PARAMETERS_PATH,
    MILP_CONFIG_PATH,
    OUTPUT_ROOT,
    PREFLIGHT_PATH,
    RESULTS_DIR,
    RUN_METADATA_PATH,
    environment_info,
    git_state,
    json_text,
    read_json,
    sha256_file,
    write_text,
)


def main() -> None:
    preflight = read_json(PREFLIGHT_PATH)
    run = read_json(RUN_METADATA_PATH)

    write_text(ENVIRONMENT_PATH, json_text({
        "environment": environment_info(),
        "environment_during_run": run["environment"],
        "git_before_final_experiment": preflight["git_before"],
        "git_after_final_experiment": git_state(),
        "note": "The experiment folders are untracked in git, so the commit alone does not "
                "identify them; file_hash_manifest.json does.",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }))

    files = {
        "dataset": DATASET_PATH,
        "config": CONFIG_PATH,
        "frozen_parameters": FROZEN_PARAMETERS_PATH,
        "milp_config": MILP_CONFIG_PATH,
    }
    hashes = {name: {"path": path.name, "sha256": sha256_file(path)} for name, path in files.items()}

    scripts = {f"scripts/{p.name}": sha256_file(p) for p in sorted((FINAL_ROOT / "scripts").glob("*.py"))}
    results = {f"results/{p.name}": sha256_file(p) for p in sorted(RESULTS_DIR.glob("*"))
               if p.is_file() and p != FILE_MANIFEST_PATH}
    readme = OUTPUT_ROOT / "README.md"

    write_text(FILE_MANIFEST_PATH, json_text({
        "key_files": hashes,
        "scripts": scripts,
        "results": results,
        "readme": sha256_file(readme) if readme.exists() else None,
        "scripts_unchanged_since_preflight": all(
            preflight["final_code_hashes"].get(k) == v for k, v in scripts.items()),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }))
    print(f"Wrote {ENVIRONMENT_PATH.name} and {FILE_MANIFEST_PATH.name}")


if __name__ == "__main__":
    main()
