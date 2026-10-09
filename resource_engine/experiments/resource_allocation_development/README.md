# AASHRAY Resource Allocation: Development Experiment (3,000 scenarios)

## 1. Purpose

This is the **development / parameter-selection** stage. It tunes the
AASHRAY parameters `alpha, k, m, n` on 3,000 new synthetic scenarios and
**freezes** them in `results/frozen_parameters.json`.

It is **not** the final hypothesis test. No H0/H1 decision, p-value or
confidence interval is produced here, and the development differences
between policies are **in-sample**: the winner is chosen on these same
scenarios, so its performance here is optimistic.

**The future 12,000-scenario final test set is untouched.** It was not
generated, read or used. The generator refuses any size other than 3,000.

## How to run

From the repository root:

```bash
python experiments/resource_allocation_development/scripts/generate_development_dataset.py
python experiments/resource_allocation_development/scripts/generate_parameter_grid.py
python experiments/resource_allocation_development/scripts/evaluate_configurations.py
python experiments/resource_allocation_development/scripts/validate_development.py
```

`validate_development.py` writes `frozen_parameters.json` **only if every
validation check passes**, and never overwrites an existing frozen file.

## 2. Pilot vs development

| | Pilot (500) | Development (3,000) |
|---|---|---|
| Role | diagnostic only | parameter selection |
| Master seed | 20261007 | 20261108 (+ namespace `aashray-resource-allocation-development`) |
| GT rule | `0.5*S + 0.5*U > 0.8` (retired) | `(S>=0.8 AND U>=0.8) OR S>=0.95 OR U>=0.95` |
| Scenarios with no GT-critical emergency | 212 (42%) | 0 (guaranteed) |
| Scarcity | LOW 120 / MODERATE 150 / HIGH 230 | LOW 300 / MODERATE 1,200 / HIGH 1,500 |
| Policies | FCFS, AASHRAY (provisional), reverse, random | FCFS, LINEAR, 726 AASHRAY candidates |

Carried over from the pilot: TDC is order-invariant for this allocator, so it
is descriptive only; CDC is the selection objective; LOW scarcity produces no
order variation, so it is kept small.

The existing allocator is used **unchanged**, through the same mechanism as
the pilot (`scripts/allocator_adapter.py`): the public `allocate_batch` with
identical placeholder priority inputs, so its own ranking ties and its stable
sort keeps the experiment's order. The order is verified on every call.

## 3. Dataset generation

`scripts/generate_development_dataset.py` follows the validated pilot design.

- **Strata:** scarcity × size × S-U profile. Each scarcity level is spread
  evenly over the 15 size × profile cells (LOW 20, MODERATE 80, HIGH 100 per
  cell). Sizes: SMALL 3–6, MEDIUM 8–14, LARGE 18–30 emergencies; 2–5
  warehouses per scenario.
- **Scarcity:** total supply per resource type = ratio × total demand, with
  the ratio drawn from LOW `[1.15, 1.60]` (ceil, so supply > demand),
  MODERATE `[0.90, 1.10]` (round) or HIGH `[0.30, 0.70]` (floor, so
  supply < demand).
- **Severity / urgency:** 4 decimals, `0 < S, U <= 1`. Each emergency
  belongs to a stratum (LL, LH, HL, HH, MM, MIXED) and S and U are drawn
  **independently** within it. Each scenario's S-U profile sets the stratum
  mixture (LL/LH/HL/HH-dominant or MODERATE_MIXED).
- **Demand:** the existing resource types (water, food, medical_kits) and
  per-person rates (read-only from `resource_services/config/resource_rules.json`),
  a required-type pattern per emergency, integer quantities. Independent of
  S, U, GT labels, arrival and all AASHRAY parameters.
- **Arrival:** an independent integer offset in [0, 3600] s per emergency.
- **Independent random streams** per scenario: structure, severity/urgency,
  arrival, demand, inventory, location; all derived with sha256 from the
  master seed and namespace.

### Guarantee of at least one GT-critical emergency

Rejection sampling of the **severity/urgency stream only**. Attempt 0 uses
the stream `sha256(scenario_seed | "severity_urgency" | 0)`. If no emergency
is GT-critical under the fixed rule, the whole S/U draw is repeated with
attempt 1, 2, … until one is. Arrival, demand and inventory use their own
streams and are unaffected. Only the fixed GT rule is consulted, never an
AASHRAY score. The attempt count is stored per scenario
(`su_generation_attempts`).

## 4. Ground-truth criticality (new, fixed)

```
GT_critical = 1  if  (S >= 0.8 AND U >= 0.8)  OR  S >= 0.95  OR  U >= 0.95
              0  otherwise
```

This is a **predefined experimental reference rule**, fixed before any
development result. It is **not** an externally validated medical or
disaster-management truth, and it does not depend on `alpha, k, m, n`.
Every emergency stores its label and the rule inputs (`gt_rule_inputs`: S,
U, thresholds and which clause fired).

## 5–7. Policies

All three allocate through the same unchanged allocator on the same
inventory and demand. Only the order differs.

- **FCFS:** ascending `(arrival_timestamp, emergency_id)`. It receives only
  `(emergency_id, arrival_timestamp)` and cannot see S, U, GT labels,
  scores or parameters.
- **LINEAR:** descending `P_linear = 0.5*S + 0.5*U`; ties in FCFS order.
- **AASHRAY:** descending `P_o = k*S + m*U + n*P_n` with
  `P_n = S^alpha * U^(1-alpha)`; ties in FCFS order. Continuous score only;
  no priority categories affect allocation.

**Ties:** scores within `1e-12` of each other are tied and go to FCFS order.
See "Correction during development" below.

**Note:** LINEAR is itself a grid point (`k = m = 0.5, n = 0`, any alpha).
The selected configuration's development mean CDC therefore **cannot be
below LINEAR's by construction**.

## 8. Parameter grid

`alpha ∈ {0.0, 0.1, …, 1.0}` and `k, m, n ∈ {0.0, 0.1, …, 1.0}` with
`k + m + n = 1`, built from integer tenths so the sum is exact. That gives
66 weight triples × 11 alphas = **726 candidates**, written to
`results/candidate_grid.csv` (with `config_id` in ascending
`(alpha, k, m, n)` order) **before** any evaluation. The grid is checked
against the generator before evaluation and again during validation.

## 9. Ranking equivalence

Only the induced order affects allocation. For every candidate and every
scenario, the full ordered emergency-id sequence is computed. A
configuration's signature is its sequence in **all 3,000 scenarios**;
configurations with identical signatures form one **empirical
ranking-equivalence class** (`results/ranking_equivalence.csv`).

One representative per class (its lowest `config_id`) is evaluated. Within
a scenario, an order that occurs more than once is passed to the allocator
once and its result reused, since the allocator is deterministic for a given
order. Every class member receives the class's metrics in
`results/configuration_results.csv`.

## 10–11. Metrics

- **CDC (selection objective):** fulfilled demand of GT-critical
  emergencies ÷ required demand of GT-critical emergencies, from the
  allocator's actual quantities. Membership comes only from the fixed GT
  label. Defined for every scenario, because each has ≥1 GT-critical
  emergency.
- **TDC (descriptive only):** total fulfilled ÷ total required. Not used for
  selection.
- Demand is summed over the three resource types in native units, as in the
  pilot, so water dominates.
- Percentiles use linear interpolation between order statistics (numpy's
  default); the standard deviation is the sample standard deviation.

## 12. Winner-selection rule (applied mechanically)

1. Highest **mean CDC** over all 3,000 scenarios.
2. Configurations whose mean is within `1e-6` of the best mean are tied;
   among them, highest **median CDC** (within `1e-6` = tied).
3. Then highest **10th-percentile CDC** (within `1e-6` = tied).
4. Then the lexicographically smallest `(alpha, k, m, n)`.

TDC, the baselines, individual scenarios and researcher judgement play no
part. The baselines are compared **after** selection.

## 13. Reproducibility

The master seed, namespace and every derived seed are stored. Regenerating
with the stored config gives byte-identical scenario data (validation check
17). Per-scenario results are written as gzip with `mtime=0`.

## 14. Freeze procedure

`validate_development.py` runs 20 required checks and 3 consistency checks.
If any fails it **stops** and nothing is frozen. If all pass, it writes
`results/frozen_parameters.json` with the parameters, the selection rule and
trace, the development scores, seeds, hashes, a timestamp and the git commit,
plus the statement:

> These parameters were selected using the development dataset only. They
> must not be changed after the final test dataset is evaluated.

The frozen file is the **only** source the final test experiment should
read. It is never overwritten once written.

## 15. Final test set

The 12,000-scenario final test set was **not** generated, accessed or used,
and nothing here was tuned against it. It must use a master seed and
namespace different from both the pilot and this development experiment.

## Development results (in-sample, descriptive only)

All figures come from `results/`. They are development (selection-sample)
results, not final hypothesis evidence.

**Dataset.**
- **Size:** 3,000 scenarios (LOW 300, MODERATE 1,200, HIGH 1,500; SMALL,
  MEDIUM and LARGE 1,000 each) and 39,409 emergencies (3–30 per scenario,
  mean 13.14).
- **GT-critical:** 7,019 emergencies (17.8%); all 3,000 scenarios have ≥1
  (1–14 per scenario, median 2). 855 scenarios needed an S/U redraw (max 25
  attempts).
- **Independence:** Pearson r(S, U) = −0.005. FCFS position vs S, U and GT
  has |r| ≤ 0.003.

**Search.** 726 candidates collapse into **506** empirical
ranking-equivalence classes: 495 singletons plus 11 classes of 21
configurations each. These are exactly the 11 linear functions
`k'S + m'U`, reached through `n = 0`, `alpha = 0` or `alpha = 1`. 506
representatives were evaluated, with 345,335 allocator calls (order
verified on each).

**Winner (automatic):** `C045 — alpha 0.0, k 0.5, m 0.0, n 0.5`. Mean CDC
0.9490, median 1.0, 10th percentile 0.8106.

> **The winning class (R006) is the LINEAR baseline's class.** With
> `alpha = 0`, `P_n = U`, so the frozen `P_o = 0.5*S + 0.5*U`, which is exactly
> `P_linear`. All 21 configurations in the class compute that same function;
> the tie-break rule picked C045 among them, so `n = 0.5` has no effect
> beyond weighting U. Every configuration where the geometric term matters
> (`n > 0`, `0 < alpha < 1`) scored **lower**. The best of them, C115
> (`alpha 0.1, k 0.5, m 0.4, n 0.1`), reached 0.9460 (−0.0030).
>
> The development data therefore identifies only the function
> `0.5*S + 0.5*U`, not unique values of `alpha, k, m, n`.

| Policy | Mean CDC | Median | P10 |
|---|---|---|---|
| FCFS | 0.7261 | 0.9950 | 0.0027 |
| LINEAR | 0.9490 | 1.0000 | 0.8106 |
| AASHRAY (frozen) | 0.9490 | 1.0000 | 0.8106 |

Paired per-scenario CDC differences:

- **AASHRAY − FCFS:** mean +0.2229. Higher in 1,407 scenarios, lower in 97,
  equal in 1,496.
- **AASHRAY − LINEAR:** 0 in all 3,000 scenarios (the same function).

| Scarcity | FCFS | LINEAR | AASHRAY | AASHRAY − FCFS |
|---|---|---|---|---|
| LOW | 1.0000 | 1.0000 | 1.0000 | 0 (300 equal) |
| MODERATE | 0.9706 | 0.9985 | 0.9985 | +0.0279 (288 higher, 9 lower) |
| HIGH | 0.4757 | 0.8993 | 0.8993 | +0.4236 (1,119 higher, 88 lower) |

**TDC (descriptive):** mean 0.7385 and median 0.7991 for every policy. TDC
did not vary across any evaluated order in any scenario, confirming the
pilot finding.

**Implication for the final test (not acted on here):** with these frozen
parameters, AASHRAY and LINEAR are the same policy. A final AASHRAY-vs-LINEAR
comparison would show a difference of exactly zero by construction; only
the comparison against FCFS remains informative.

## Correction during development

The first full evaluation run was **stopped before it finished, and none of
its results were read**. Its ranking step reported 558 empirical
equivalence classes, while the grid contains only 506 mathematically
distinct score functions (`n = 0`, `alpha = 0` and `alpha = 1` all reduce
to a linear `k'S + m'U`).

The cause was floating-point rounding. Mathematically equal scores, for
example `0.1·0.9171 + 0.9·0.879` and `0.1·0.8325 + 0.9·0.8884` (both
0.88281), can differ in the last bit. The order of those emergencies then
followed rounding noise instead of the specified FCFS tie rule. In scenario
DEV-0176 this put a later arrival first.

Fix: scores within `1e-12` are treated as ties. S and U have 4 decimals and
the weights are tenths, so genuinely different scores differ by far more
than that; the tolerance only absorbs rounding error (~1e-16). With the fix,
the empirical classes correspond one-to-one to the 506 mathematical
functions. The dataset, grid, GT rule and selection rule were not changed.

Every file in `results/` comes from the corrected run only.
