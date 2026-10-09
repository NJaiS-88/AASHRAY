"""Generate and store the fixed candidate grid BEFORE any evaluation.

Usage (from the repository root):

    python experiments/resource_allocation_development/scripts/generate_parameter_grid.py

alpha in {0.0, 0.1, ..., 1.0} and k, m, n in {0.0, 0.1, ..., 1.0} with
k + m + n = 1. Values are built from integer tenths so the sum is exact.
11 alpha values x 66 weight combinations = 726 candidates, with config_id
assigned in ascending (alpha, k, m, n) order.
"""

import csv
import io

from dev_common import GRID_PATH, write_text


GRID_FIELDS = ["config_id", "alpha", "k", "m", "n"]

EXPECTED_CANDIDATES = 726


def build_grid() -> list[dict]:
    weights = [
        (k_tenths, m_tenths, 10 - k_tenths - m_tenths)
        for k_tenths in range(11)
        for m_tenths in range(11 - k_tenths)
    ]

    candidates = sorted(
        (alpha_tenths / 10, k / 10, m / 10, n / 10)
        for alpha_tenths in range(11)
        for k, m, n in weights
    )

    grid = [
        {
            "config_id": f"C{index:03d}",
            "alpha": alpha,
            "k": k,
            "m": m,
            "n": n,
        }
        for index, (alpha, k, m, n) in enumerate(candidates)
    ]

    if len(grid) != EXPECTED_CANDIDATES:
        raise ValueError(f"Grid has {len(grid)} candidates, expected 726.")

    return grid


def grid_text(grid: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=GRID_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(grid)
    return buffer.getvalue()


def read_grid() -> list[dict]:
    with GRID_PATH.open("r", encoding="utf-8") as file:
        return [
            {
                "config_id": row["config_id"],
                "alpha": float(row["alpha"]),
                "k": float(row["k"]),
                "m": float(row["m"]),
                "n": float(row["n"]),
            }
            for row in csv.DictReader(file)
        ]


def main() -> None:
    grid = build_grid()
    write_text(GRID_PATH, grid_text(grid))
    print(f"Wrote {GRID_PATH} ({len(grid)} candidates)")


if __name__ == "__main__":
    main()
