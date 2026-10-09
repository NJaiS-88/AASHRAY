# AASHRAY Resource Allocation: Final Held-Out Evaluation (12,000 scenarios)

The **final, pre-registered evaluation** of the AASHRAY resource-allocation
hypothesis. All conclusions here come **only** from the 12,000 held-out
scenarios. Pilot and development results are not combined with them.

- **Research question:** does severity–urgency priority allocation improve
  critical-demand coverage over arrival-time FCFS under constrained
  resources, and how close is it to the optimal allocation under the same
  constraints?
- **H1 (effectiveness, primary):** `H0: mean(CDC_AASHRAY − CDC_FCFS) <= 0`
  vs `H1: > 0`, at α = 0.05.
- **H2 (near-optimality):** AASHRAY's gap to the MILP optimum. Descriptive;
  no superiority test against the MILP.
- **H3 (computational cost):** AASHRAY vs MILP runtime on the same scenarios
  and machine. Descriptive.

## Pre-registration and order of execution

Every setting was fixed in `config/final_config.json` **before** any final
data existed. The pre-flight then hashed the config and all scripts, and
validation proves none of them changed afterwards (check 26). The pipeline
ran once, in this order:

| Phase | Script | Result |
|---|---|---|
| — | `build_final_config.py` | config derived mechanically from the development config |
| A | `preflight.py` | 8/8 checks; protected manifest, code hashes, environment, git state |
| B | `generate_final_dataset.py` | generator equivalence proven; 12,000 scenarios generated, validated (10/10), frozen read-only |
| C | `run_final_experiment.py` | FCFS, AASHRAY and MILP on all 12,000 scenarios (94.5 s) |
| D | `validate_final.py --gate` | 35/35 critical checks before any statistics |
| E–F | `analyze_final.py` | statistics and summaries, computed only from the master CSV |
| G | `validate_final.py` | 37/37, including independent recomputation and exact reproduction of the tests |
| — | `write_manifest.py` | environment and file-hash manifest |

Before the official run, the complete pipeline was dry-run on a throwaway
180-scenario dataset (seed 1, separate namespace, scratch folder) to test the
code. **No final data existed during the dry run.** The dry run found one
recording bug: `scipy.optimize.milp` removes `"disp"` from the options dict
it is given, which altered the recorded options. It was fixed by passing
each solve a copy; solver behaviour is unaffected because `disp` defaults to
`False`. The scripts were then frozen.

## Design (identical to development except seed, namespace, counts)

- **Seed:** master seed `20261209`, namespace
  `aashray-resource-allocation-final`. Both differ from the pilot
  (20261007) and the development set (20261108).
- **Scarcity:** LOW 1,200, MODERATE 4,800, HIGH 6,000. Each is spread
  evenly over the same 15 size × S-U-profile cells as development (80, 320
  and 400 per cell).
- **Generator:** a verbatim copy of the development generator (the original
  caps its size at 3,000). **Proven unchanged:** run with the development
  config, the copy reproduces the development dataset **byte for byte**
  (`results/generator_equivalence.json`). Only identifier labels (`FIN-`
  prefix, 5-digit index, warehouse display name) differ; they feed no
  random stream.
- **≥1 GT-critical emergency per scenario:** the same deterministic S/U
  redraw mechanism as development. 0 scenarios have undefined CDC.
- **GT rule (frozen development rule):**
  `GT_critical = 1 if (S >= 0.8 AND U >= 0.8) OR S >= 0.95 OR U >= 0.95`.
  This is a predefined reference rule, not an externally validated truth.
  The retired pilot rule is not used.
- **Dataset:** `data/final_12000_scenarios.json`, frozen read-only before
  any method ran. SHA-256
  `39912ec07be7cc7e3bde609a65d9019322a014dfde7a15bf769f18f087db7bab`.

## Methods (validated implementations, imported read-only)

- **FCFS:** development `policies.fcfs_order`; ascending
  `(arrival_timestamp, emergency_id)`.
- **AASHRAY:** development `policies.aashray_order` with the frozen
  parameters (C045: `alpha 0.0, k 0.5, m 0.0, n 0.5`), read from
  `frozen_parameters.json`. **This ranking is exactly `0.5·S + 0.5·U`**;
  validation confirms every AASHRAY order equals an independent ranking by
  that score (check E5). Conclusions about "AASHRAY" are conclusions about
  this ranking; the geometric term plays no part.
- **Allocation:** FCFS and AASHRAY orders go to the unchanged
  `ResourceAllocationService.allocate_batch`, so the two differ only in
  order.
- **MILP:** the validated `milp_model.run_scenario` (HiGHS 1.12.0 via
  SciPy 1.18.0, `mip_rel_gap = 0`), unmodified. It is the optimality
  reference, not a competing heuristic.

## Metrics, tests and edge cases

- **CDC** = fulfilled ÷ required demand of GT-critical emergencies (primary).
  **TDC** is reported for FCFS and AASHRAY only. MILP total fulfilment is
  stored only as `milp_tdc_solver_dependent`; it is **not** a benchmark.
- **Primary test:** one-sided paired sign-flip permutation test on
  mean(Δ). 100,000 permutations, seed 20261210,
  `p = (1 + count) / (100,000 + 1)`.
- **95% CI:** paired percentile bootstrap, 10,000 resamples, seed 20261211.
- **Secondary test:** one-sided Wilcoxon signed-rank, zero differences
  dropped and counted, normal approximation.
- **Effect size:** Cohen's dz (sample SD), win/tie/loss rates, and
  probability of superiority = (wins + ½ ties) / n.
- **Ties:** `|Δ| <= 1e-9`.
- **Optimality gap:** `(CDC_MILP − CDC_AASHRAY) / CDC_MILP`. It would be
  defined as 0 if CDC_MILP were 0; that never occurred.
- **Relative improvement:** NaN when CDC_FCFS = 0 (1,080 scenarios), never
  infinity.

## Results (12,000 held-out scenarios)

### Overall (Table 1)

| Metric | FCFS | AASHRAY | MILP |
|---|---|---|---|
| Mean CDC | 0.7363 | 0.9477 | 0.9817 |
| Median CDC | 0.9946 | 1.0000 | 1.0000 |
| Std CDC | 0.3604 | 0.1524 | 0.0734 |
| Mean TDC | 0.7394 | 0.7394 | N/A (not an optimization benchmark) |
| Mean runtime (ms) | 0.429 | 0.248 | 2.473 |
| Median runtime (ms) | 0.279 | 0.213 | 1.385 |
| P95 runtime (ms) | 0.772 | 0.488 | 7.087 |

### H1: AASHRAY vs FCFS (Table 3)

| | Value |
|---|---|
| Valid pairs | 12,000 (0 undefined) |
| Mean paired difference | **+0.2114** (+21.14 percentage points) |
| Relative improvement of means | +28.7% |
| Median paired difference | 0.0 (half the scenarios are ties) |
| 95% bootstrap CI | **[0.2053, 0.2177]** |
| Permutation p (primary) | **9.9999 × 10⁻⁶**: none of 100,000 sign-flipped means reached the observed mean; this is the smallest attainable p, so p ≤ 1.0 × 10⁻⁵ |
| Wilcoxon p (secondary) | reported as 0.0: below double-precision range (W⁺ = 17,244,745.5; 6,004 non-zero, 5,996 zero differences) |
| Cohen's dz | 0.603 |
| AASHRAY wins / ties / FCFS wins | 5,656 (47.13%) / 5,996 (49.97%) / 348 (2.90%) |
| Probability of superiority | 0.721 |

**Conclusion (pre-registered rule):** reject H0 at α = 0.05. On the held-out
set, the mean CDC difference (AASHRAY − FCFS) is significantly greater than
0.

### By scarcity (Table 2)

| Scarcity | n | FCFS CDC | AASHRAY CDC | MILP CDC | AASHRAY − FCFS | Mean gap to MILP |
|---|---|---|---|---|---|---|
| LOW | 1,200 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 |
| MODERATE | 4,800 | 0.9709 | 0.9983 | 0.9995 | +0.0274 | 0.0012 |
| HIGH | 6,000 | 0.4958 | 0.8968 | 0.9637 | +0.4009 | 0.0691 |

Win / tie / loss against FCFS:

- **LOW:** all 1,200 tied.
- **MODERATE:** 24.58% wins, 74.56% ties, 0.85% FCFS wins.
- **HIGH:** 74.60% wins, 20.28% ties, 5.12% FCFS wins.

The descriptive 95% bootstrap intervals for the difference are MODERATE
[0.0248, 0.0301] and HIGH [0.3906, 0.4112]. The only hypothesis test is the
overall one. The order effect is absent under LOW scarcity and largest under
HIGH scarcity.

### H2: optimality (Table 4)

- **Gap distribution:** mean 0.0350, median 0, P90 0.0487, P95 0.2441, max
  1.0.
- **Closeness:** exact optimum in 86.66% of scenarios; within 1% in 88.41%,
  within 5% in 90.05%, within 10% in 91.50%.
- **By scarcity:** LOW 100% exact; MODERATE 98.27%; HIGH 74.70% (mean gap
  0.0691, P95 0.4634).
- **Worst cases:** in 59 scenarios AASHRAY covered no critical demand while
  the MILP did (gap = 1.0). Non-critical emergencies with a high
  `0.5·S + 0.5·U` score took the scarce stock first.

### H3: computational cost (Table 5)

- **AASHRAY:** mean 0.248 ms, median 0.213 ms, P95 0.488 ms; total 2.97 s for
  12,000 scenarios.
- **MILP:** mean 2.473 ms, median 1.385 ms, P95 7.087 ms; total 29.67 s.
- **Speedup (MILP ÷ AASHRAY):** 9.99× by total, 6.49× by median. The
  per-scenario ratio has median 7.44 and minimum 1.41. AASHRAY was faster in
  all 12,000 scenarios.

**Caveat (execution order).** Pre-registered order runs FCFS first in each
scenario, right after the allocator is constructed, and AASHRAY second. Both
make the identical allocator call, yet the first-position (FCFS) allocation
was slower in 11,645 of 12,000 scenarios: mean 0.420 ms against 0.228 ms. This
is consistent with a cold-start or cache effect, so AASHRAY's measured time
is likely favourable. A **conservative** estimate, pairing AASHRAY's own
decision time with the first-position allocation time, gives:

- mean 0.440 ms, median 0.289 ms per scenario;
- MILP still **5.6× slower by total and 4.8× by median**, and slower in
  11,995 of 12,000 scenarios.

Five FCFS runs exceeded 140 ms (maximum 292 ms), most likely OS or
garbage-collection pauses. They inflate FCFS's mean and maximum.
FCFS-vs-AASHRAY runtime differences should therefore not be interpreted;
they were not a pre-registered comparison.

## Validation and integrity

- **MILP:** 12,000 / 12,000 proven optimal (status 0, gap 0, bound closed);
  12,000 / 12,000 equal the independent analytical optimum.
- **Constraints:** no supply or demand violations, no negative or
  non-integral allocations.
- **Recomputation:** CDC and TDC recomputed independently from the allocation
  files and dataset labels match exactly. No CDC or TDC exceeds 1, and
  AASHRAY and FCFS never exceed the MILP.
- **Reproducibility:** summary values match an independent recomputation from
  the master CSV (tolerance 1e-9). Permutation, bootstrap, Wilcoxon and
  effect-size results reproduce **exactly** from the raw differences.
- **Integrity:**
  - application, pilot, development and MILP files unchanged;
  - frozen parameters unchanged;
  - config and scripts unchanged since pre-flight;
  - dataset untouched after freeze;
  - no scenario dropped or re-run;
  - one AASHRAY configuration evaluated; no tuning.

## Notes for interpretation

- AASHRAY here is the ranking `0.5·S + 0.5·U`, selected on development data
  before this test; the result is about that policy.
- **TDC is identical for FCFS and AASHRAY** in every stratum (mean 0.7394).
  This is consistent with the earlier finding that TDC is structurally
  order-invariant under this allocator.
- **The MILP optimum equals the closed form `Σ_r min(critical demand, supply)`**
  under this fungible, unconstrained allocator model. The near-optimality
  result is relative to that model only. It says nothing about vehicles,
  routes, time or compatibility, none of which the allocator has.
- **The median difference is 0** because half of all scenarios are ties:
  every LOW scenario and most MODERATE ones, where supply suffices
  regardless of order.

## Files

| File | Purpose |
|---|---|
| `config/final_config.json` | Every pre-registered setting |
| `data/final_12000_scenarios.json` | Frozen held-out dataset (read-only) |
| `results/final_scenario_results.csv` | **Master table**: one row per scenario, 57 columns; reproduces every table, graph and test |
| `results/final_policy_allocations.csv.gz` | FCFS and AASHRAY order, AASHRAY score and per-emergency allocation |
| `results/final_milp_allocations.csv.gz` | Every non-zero MILP allocation x[e,r,w] |
| `results/final_method_summary.csv` | One row per method: CDC distribution, TDC, gap, runtime percentiles |
| `results/final_scarcity_summary.csv` | One row per scarcity × method |
| `results/final_win_tie_loss.csv` | Win/tie/loss overall and by scarcity (Graph 8) |
| `results/final_statistical_tests.json` | Exact inputs and outputs of every test |
| `results/final_summary.json` | All results, paper tables 1–5 and the graph index |
| `results/validation_report.json` | 37 final checks |
| `results/gate_report.json` | Phase D gate (35 checks) |
| `results/preflight.json`, `protected_manifest.json` | Phase A record and protected-file hashes |
| `results/generator_equivalence.json` | Proof that the copied generator reproduces development byte for byte |
| `results/dataset_freeze.json` | Dataset hash, freeze time, pre-freeze checks |
| `results/run_metadata.json` | Run ID, timing methodology, warm-up, environment |
| `results/environment.json` | CPU, RAM, OS, Python, SciPy, HiGHS, git before and after |
| `results/file_hash_manifest.json` | SHA-256 of the dataset, config, frozen parameters, scripts and results |
| `scripts/*.py` | The pipeline listed above |

Graphs 1–10 map to columns as listed in `final_summary.json` →
`graph_index`. MILP TDC must not be plotted as a benchmark.
