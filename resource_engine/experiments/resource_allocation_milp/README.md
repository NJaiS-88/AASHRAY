# AASHRAY Resource Allocation: MILP Benchmark

An **exact optimisation benchmark** for the AASHRAY resource-allocation
experiment: the most GT-critical demand any allocation could fulfil in a
scenario.

**MILP does not participate in AASHRAY parameter selection.** The frozen
parameters (`experiments/resource_allocation_development/results/frozen_parameters.json`)
were selected before this benchmark existed. They are only read here to
confirm they are unchanged, never used or modified. No hypothesis test is
performed, and the future 12,000-scenario test set was not generated or
accessed.

## How to run

From the repository root:

```bash
python experiments/resource_allocation_milp/scripts/hand_check_tests.py
python experiments/resource_allocation_milp/scripts/solve_milp.py
python experiments/resource_allocation_milp/scripts/validate_milp.py
```

Each step stops (exit code 1) if its checks fail. `solve_milp.py` refuses to
run unless all hand checks passed, and only starts the full run if the
50-scenario subset is entirely proven optimal and equal to the analytical
optimum.

## 1. Why MILP

AASHRAY ranks emergencies and lets the existing greedy allocator serve them
in that order. The MILP instead computes the **best possible** allocation
for the same scenario, so AASHRAY's distance from the optimum (optimality
gap) and its computational cost can be measured against an explicit
optimisation formulation.

## 2–5. Formulation (`scripts/milp_model.py`)

The problem is the one the current allocator faces, and nothing more.

- **Decision variables:** `x[e,r,w] >= 0`, integer. The quantity of resource
  type `r` (water, food, medical_kits) sent from warehouse `w` to emergency
  `e`, over the full index set with no pre-elimination. No binary variables
  are needed.
- **Objective:** `maximize Σ_{e,r,w} GT_critical[e] · x[e,r,w]`.
- **Supply constraints:** for every warehouse `w` and type `r`,
  `Σ_e x[e,r,w] <= available[w,r]`.
- **Demand constraints:** for every emergency `e` and type `r`,
  `Σ_w x[e,r,w] <= demand[e,r]`. Where demand is 0, this forces `x = 0`.
- **Nothing else.** There are no vehicle, compatibility, distance, travel
  time, route, personnel, shelter, road, response-time, priority-category
  or AASHRAY-score constraints, because the current allocator has none.

## 6. GT criticality

The stored, frozen development label:

```
GT_critical = 1 if (S >= 0.8 AND U >= 0.8) OR S >= 0.95 OR U >= 0.95, else 0
```

The MILP reads the label. It never uses `alpha, k, m, n`, an AASHRAY score,
FCFS or the linear S+U score.

## 7–8. Why CDC is the objective and TDC is not

The total required GT-critical demand of a scenario is fixed, so maximising
critical fulfilment is the same as maximising **CDC**, the experiment's
primary metric.

TDC is not optimised. The objective gives non-critical demand zero weight,
so **any** split of leftover stock among non-critical emergencies is equally
optimal, and the solver picks one arbitrarily. The MILP's total fulfilment
and TDC are therefore stored only as `*_solver_dependent` and are **not**
benchmark values. HiGHS usually sends nothing to non-critical emergencies;
the mean "TDC" on development data is 0.20.

## 8. CDC

```
critical_required  = Σ_e Σ_r GT_critical[e] · demand[e,r]
critical_fulfilled = Σ_e Σ_r Σ_w GT_critical[e] · x[e,r,w]
critical_unmet     = critical_required − critical_fulfilled
CDC_MILP           = critical_fulfilled / critical_required
```

If `critical_required == 0`, CDC is **NaN** (written as `NaN`), never 0 or 1.

## 9. Analytical optimum (independent oracle, `scripts/analytical_optimum.py`)

Stock is fungible, any warehouse can supply any emergency, and resource types
are not coupled. So the most critical demand that can be met is

```
analytical_optimum = Σ_r min( Σ_e GT_critical[e] · demand[e,r],  Σ_w available[w,r] )
```

This shares no code with the MILP and is used **only** to validate it. Every
proven-optimal MILP solution must equal it exactly.

**The MILP is mathematically equivalent to this closed form** under the
current allocator model. The constraint matrix is a transportation
(bipartite network) matrix, which is totally unimodular, so the LP
relaxation already has an integral optimum: all 3,000 development scenarios
solved at the root node. The MILP is kept because the experiment
benchmarks AASHRAY against an explicit optimisation formulation. No
artificial constraints were added to make it harder.

A related consequence: under the existing greedy allocator, **any order that
serves every GT-critical emergency before every non-critical one reaches this
optimum.** Per resource type, the critical emergencies then receive
`min(critical demand, supply)` between them.

## 10. Solver

**HiGHS 1.12.0 via `scipy.optimize.milp` (SciPy 1.18.0).** It is the only
exact MILP solver available in the environment; OR-Tools, PuLP, highspy,
Pyomo, python-mip, CVXPY and Gurobi are not installed, and nothing was
installed. Options: `mip_rel_gap = 0`, `time_limit = 60 s`,
`presolve = true` (`config/milp_config.json`). The relative gap is 0 because
HiGHS otherwise stops at a 1e-4 gap. Environment details are in
`results/solver_environment.json`.

## 11. Optimality

A solve is a **proven optimum** only if status = 0 ("Optimal"),
`success = true`, `mip_gap = 0` and `|objective − dual bound| <= 1e-6`.
Anything else, including a time-limited incumbent, is **NON-OPTIMAL** and is
never reported as an optimum. Validation tests this with synthetic cases and
with a real solve forced to its time limit (HiGHS status 1, correctly
labelled non-optimal).

Integrality: HiGHS returns floating-point values; each `x` is rounded to the
nearest integer and the deviation recorded (maximum on development data:
0.0). All reported quantities and constraint checks use the rounded
integers.

## 12. Runtime measurement

`time.perf_counter` (monotonic, high resolution). Recorded per scenario:

- `model_build_time_seconds`: scenario → MILP arrays (objective, sparse
  constraint matrix, bounds, integrality).
- `solver_time_seconds`: the `scipy.optimize.milp` call.
- `total_milp_time_seconds`: the sum of the two.

File loading, dataset generation, start-up and result extraction are
excluded. One unrecorded warm-up solve runs first, so library loading is not
timed. Millisecond-scale timings are noisy and machine-specific; the
AASHRAY-vs-MILP comparison must run on the same machine and environment.

## 13–14. Relationship to AASHRAY

AASHRAY decides an **order**; the existing allocator turns it into
quantities. The MILP decides **quantities** directly and optimally. On the
same scenario:

- CDC gap = `CDC_MILP − CDC_AASHRAY` (≥ 0 by construction);
- time = AASHRAY decision + allocation time vs MILP build + solve time.

The MILP is a benchmark, not a tuner. It was run after the parameters were
frozen, and nothing about it feeds back into `alpha, k, m, n`.

## 15. Use on the 12,000-scenario final test

The future final-test runner should call, for each test scenario:

```python
from milp_model import run_scenario          # build + solve + extract
from analytical_optimum import analytical_optimum
outcome = run_scenario(scenario, options)    # options from config/milp_config.json
```

It should then require `outcome["is_proven_optimum"]` and
`outcome["critical_fulfilled"] == analytical_optimum(scenario)["analytical_optimum"]`,
exactly as `solve_milp.py` does. Scenarios must use the same schema as the
development data. The final test set itself does not exist yet and was not
touched.

## Development benchmark results

From `results/development_milp_summary.json`. Benchmark validation only.

- **Solved:** 3,000 / 3,000, all **proven optimal** (status 0, gap 0, closed
  bound); 0 non-optimal or failed. The 50-scenario subset passed first.
- **Analytical optimum:** 3,000 match, 0 mismatch.
- **MILP CDC:** mean 0.9818, median 1.0, min 0.3243, max 1.0.
  - LOW: 1.0
  - MODERATE: mean 0.9996
  - HIGH: mean 0.9639, min 0.3243
- **Time (build + solve):** mean 2.14 ms, median 1.19 ms, P95 6.43 ms, max
  9.44 ms. Solver alone: mean 1.94 ms, median 0.98 ms, P95 6.25 ms.
- **Model size:** variables mean 135.5 (18–450); constraints mean 49.8
  (15–105).
- **Determinism:** the 50 subset scenarios, solved three times, gave
  identical objectives and CDC.

## Files

- `config/milp_config.json`: formulation, solver options, optimality rule,
  timing definition.
- `scripts/`:
  - `milp_model.py`: the MILP.
  - `analytical_optimum.py`: the independent oracle.
  - `hand_check_tests.py`: the eight hand-worked tests.
  - `solve_milp.py`: the development runs.
  - `validate_milp.py`: 25 checks plus determinism.
  - `milp_common.py`: shared paths and file hashing.
- `results/`:
  - `hand_check_results.json`, `development_milp_results.csv`
  - `development_milp_allocations.csv.gz` (non-zero allocations only)
  - `development_milp_summary.json`, `solver_environment.json`
  - `validation_report.json`, `protected_manifest.json` (file hashes recorded
    before solving)
