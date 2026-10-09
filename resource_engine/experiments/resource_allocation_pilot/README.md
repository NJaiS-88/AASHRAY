# AASHRAY Resource Allocation Pilot (500 scenarios)

**Role of this experiment: PILOT ONLY.**
It validates the scenario generator, the allocation harness, FCFS, the wiring of
the proposed AASHRAY priority formulation, and whether TDC depends on
allocation order. It is **not** parameter tuning and **not** hypothesis testing.
No development (tuning) set and no final 12,000-scenario test set is created
or accessed here.

---

## How to run

From the repository root:

```bash
python experiments/resource_allocation_pilot/scripts/generate_pilot_dataset.py
python experiments/resource_allocation_pilot/scripts/run_pilot.py
python experiments/resource_allocation_pilot/scripts/validate_pilot.py
```

Standard library plus the existing `resource_services` dependencies (pydantic). No
existing application file is modified; the scripts add the repo root to
`sys.path` at runtime so `resource_services.*` imports resolve.

## Layout

```
experiments/resource_allocation_pilot/
├── README.md
├── config/pilot_config.json            all design parameters, seeds, provisional AASHRAY params
├── data/pilot_500_scenarios.json       the 500 scenarios
├── results/
│   ├── pilot_results.csv               one row per scenario x order condition (3,000 rows)
│   ├── order_sensitivity.csv           one row per scenario: TDC/CDC for every order + range/std
│   ├── pilot_summary.json              distributions, aggregated metrics, sensitivity
│   └── validation_report.json          the 18 required checks + 3 consistency checks
└── scripts/
    ├── pilot_common.py                 paths, seed derivation, fixed P_GT rule
    ├── generate_pilot_dataset.py       stratified generator
    ├── allocator_adapter.py            the ONLY code that calls the existing allocator
    ├── orderings.py                    FCFS / reverse / random / AASHRAY order functions
    ├── metrics.py                      TDC, CDC and aggregation
    ├── run_pilot.py                    runs every order condition, writes results
    └── validate_pilot.py               automated validation
```

---

## Existing allocator (inspected, used unchanged)

| Aspect | What the existing code does |
|---|---|
| Implementation | `resource_services/services/resource_allocation_service.py` → `ResourceAllocationService` |
| Resource types | `water`, `food`, `medical_kits` (`schemas/resource_requirement.py::ResourceRequirement`, all three fields required, ≥ 0) |
| Inventory | list of `Warehouse` (`schemas/warehouse.py`), `inventory[type].available`; loaded from a JSON file path |
| Emergency / demand | `AllocationRequest` (`schemas/allocation.py`): `incident_id`, `requirements`, `severity`, `urgency`, categorical `priority` |
| Compatibility rules | None. Any warehouse can supply any type; `vehicles` is loaded but never used in allocation |
| Within one emergency | Warehouses visited in file order; takes `min(available, remaining)` per type; stops when fully met |
| Partial fulfilment | Supported: `PARTIALLY_FULFILLED` + `remaining_shortage` |
| Across emergencies | `allocate_batch` builds one shared working inventory, sorts requests by its own score `0.4S + 0.4U + 0.2·categorical_priority` (stable sort, descending) and allocates in that order |
| Existing priority | Categorical `LOW/MODERATE/HIGH/CRITICAL` → 0.25/0.50/0.75/1.00, score thresholds give `final_priority_level`; these only label the output, they do not change quantities |
| Per-person demand rates | `resource_services/config/resource_rules.json` (water 2, food 1, medical_kits 0.05). Read-only reuse by the generator |

### How the experiment controls order without modifying the allocator

`allocator_adapter.py` calls the public `allocate_batch` and gives **every**
request the same placeholder `severity=0.5, urgency=0.5, priority="MODERATE"`.
The allocator's internal scores are then all equal, its stable sort keeps the
input order, and it processes emergencies exactly in the order the experiment
presents. The adapter asserts this on every call (3,000/3,000 calls verified)
and raises `AllocationOrderError` otherwise.

The allocator therefore only ever sees an emergency's id and its demand. Real
S, U, P_GT and GT labels are never passed to it. The placeholders feed only
its cosmetic output fields, which the adapter discards. Check 16 confirms that
changing the placeholder category (all four) and S/U (0.01 and 1.0) changes no
allocated quantity in any of the 500 scenarios.

---

## Dataset design

Master seed `20261007`. Each scenario seed is `sha256(master_seed | "scenario" | index)`.
Each scenario has **independent random streams** (structure, severity/urgency,
arrival, demand, inventory, location), each seeded from the scenario seed plus
a stream name. Changing one stream never shifts another (validated by check 7).

### Stratification: scarcity × size × S-U profile (45 cells)

| Scarcity | Scenarios | Supply/demand ratio per type | Rounding | Realized overall ratio |
|---|---|---|---|---|
| LOW | 120 (8 per cell) | U(1.15, 1.60) | ceil, so supply > demand | 1.19 – 1.58 (mean 1.38) |
| MODERATE | 150 (10 per cell) | U(0.90, 1.10) | round | 0.91 – 1.08 (mean 1.01) |
| HIGH | 230 (15 per cell + 1 per LARGE cell) | U(0.30, 0.70) | floor, so supply < demand | 0.31 – 0.69 (mean 0.50) |

High scarcity is deliberately over-represented (46%). The ratio is drawn per
resource type, and supply is split across 2–5 warehouses
(2: 125, 3: 112, 4: 131, 5: 132 scenarios).

| Size class | Scenarios | Emergencies per scenario |
|---|---|---|
| SMALL | 165 | 3–6 (mean 4.5) |
| MEDIUM | 165 | 8–14 (mean 11.0) |
| LARGE | 170 | 18–30 (mean 23.8) |

Total emergencies: **6,607**.

### Severity / urgency

`0 < S ≤ 1`, `0 < U ≤ 1`, 4 decimals; 0 is never generated (bands start at 0.01).
Every emergency belongs to a documented stratum, and within it **S and U are two
independent uniform draws**:

| Stratum | S band | U band | Emergencies |
|---|---|---|---|
| LL | [0.01, 0.35] | [0.01, 0.35] | 1,156 |
| LH | [0.01, 0.35] | [0.65, 1.00] | 1,202 |
| HL | [0.65, 1.00] | [0.01, 0.35] | 1,176 |
| HH | [0.65, 1.00] | [0.65, 1.00] | 1,115 |
| MM | [0.35, 0.65] | [0.35, 0.65] | 963 |
| MIXED | [0.01, 1.00] | [0.01, 1.00] | 995 |

Each scenario has an S-U profile (100 scenarios each) that sets the stratum
mixture: `LL_DOMINANT`, `LH_DOMINANT`, `HL_DOMINANT`, `HH_DOMINANT` (60% the
dominant stratum, 8% each other) and `MODERATE_MIXED` (40% MM, 40% MIXED, 5%
each corner). The design is symmetric, so there is no hidden S-U correlation:
Pearson r(S, U) = **−0.025** over all emergencies.

### Demand

Drawn from its own stream, independent of S, U and arrival. Each emergency has
a required-type pattern (ALL 2,715; WATER_FOOD 814; WATER_MEDICAL 792;
FOOD_MEDICAL 769; WATER_ONLY 531; FOOD_ONLY 527; MEDICAL_ONLY 459). For each
required type, `quantity = max(1, round(rate × affected_population × U(0.6, 1.4)))`,
with affected population in 60–600 (step 20); non-required types are 0. All
quantities are integers, so allocator arithmetic is exact.

### Arrival times and FCFS

Each emergency draws an independent integer offset in [0, 3600] s from the
arrival stream, which never sees S, U, P_GT or demand. Timestamps are
`2026-01-01T00:00:00Z + offset`.

**FCFS tie-breaker:** ascending `(arrival_offset_seconds, emergency_id)`.
Fifteen scenarios contain ties (30 emergencies share a timestamp).

Independence evidence: FCFS position vs S r = 0.0065, vs U r = 0.0094, vs
P_GT r = 0.0114. Perturbing the arrival stream changes only arrivals, and
perturbing the S/U stream leaves arrivals byte-identical.

### Fixed ground-truth criticality: predefined experimental reference rule

```
P_GT = 0.5*S + 0.5*U          ground_truth_critical = 1 if P_GT > 0.8 else 0
```

This is a **predefined reference rule**, fixed before any tuning, stored in
every emergency record, and independent of α, k, m, n. The 0.8 threshold must
not change during this experiment. P_GT is rounded to 6 decimals before the
comparison (S and U have 4 decimals, so this only removes float noise). Check
11 verifies it with exact decimal arithmetic.

- GT-critical emergencies: **816 / 6,607 (12.4%)**. LOW 212, MODERATE 244, HIGH 360.
- They come only from the HH (748) and MIXED (68) strata. LL, LH, HL and MM
  cannot exceed 0.8 by construction.
- **212 scenarios have no GT-critical emergency** (HIGH 100, MODERATE 70,
  LOW 42). CDC is undefined for them and is evaluated on the other 288.

---

## Order conditions

Same inventory, same demands; only presentation order changes.

| Condition | Order | Sees |
|---|---|---|
| FCFS | ascending (arrival, id) | id + arrival only |
| AASHRAY | descending P_o, ties → FCFS order | S, U, α, k, m, n |
| REVERSE_FCFS | reverse of FCFS | id + arrival only |
| RANDOM_1/2/3 | seeded shuffle, seed = `derive_seed(master, scenario_seed, "random_order", i)` | ids only |

**AASHRAY formulation:** `P_n = S^α · U^(1−α)`, `P_o = k·S + m·U + n·P_n`, with
α ∈ [0,1], k, m, n ≥ 0, k + m + n = 1. Continuous P_o is used for ranking; no
priority categories are used.

**Provisional pilot configuration:** `α = 0.5, k = 0.4, m = 0.4, n = 0.2`.
No α/k/m/n configuration existed in the spec or the codebase. The pilot
stopped and reported this, and these values were then **selected by the user**
(2026-10-07): k/m/n carried over from the app's
`allocation_priority.weights`, α = 0.5 (P_n = √(S·U)). They are untuned and
were chosen before the AASHRAY results were seen. Provenance is in
`config/pilot_config.json → aashray_parameters.source`.

## Metrics

- **TDC** = total fulfilled / total required, using the allocator's actual quantities.
- **CDC** = fulfilled / required demand of GT-critical emergencies (fixed P_GT labels only).
- Totals: fulfilled, unmet, critical required / fulfilled / unmet.
- **Resource utilization** is not reported by the allocator. It is derived from
  its output as fulfilled / available.
- **Order sensitivity**: per scenario, the range and population std of TDC (and
  CDC) across all six orders. A scenario "changes" if range > 1e-9.

Demand is summed across water, food and medical_kits in native units, as
specified, so water dominates TDC/CDC (see Limitations).

---

## Pilot results

### TDC is order-invariant under the current allocator

| | Scenarios | TDC changed across orders | Mean range | Max range | Max std |
|---|---|---|---|---|---|
| All | 500 | **0 (0%)** | 0.0 | 0.0 | 0.0 |
| LOW | 120 | 0 | 0.0 | 0.0 | 0.0 |
| MODERATE | 150 | 0 | 0.0 | 0.0 | 0.0 |
| HIGH | 230 | 0 | 0.0 | 0.0 | 0.0 |

TDC is identical, to the last bit, across all six orders in all 500
scenarios. The mechanism was measured, not assumed: in **3,000 / 3,000**
scenario × order runs, every resource type ended at exactly
`min(total supply, total demand)`. The allocator gives each emergency all it
can find before moving on, and nothing restricts which emergency may receive
which stock (no compatibility rules), so the total delivered per type cannot
depend on order.

**This suggests TDC should be treated as a descriptive metric, not a
parameter-optimization objective,** for this allocator.

### CDC is order-dependent

| | Scenarios with CDC defined | CDC changed across orders | Mean range | Max range |
|---|---|---|---|---|
| All | 288 | 176 (61.1%) | 0.393 | 1.0 |
| LOW | 78 | 0 (0%) | 0.0 | 0.0 |
| MODERATE | 80 | 46 (57.5%) | 0.075 | 1.0 |
| HIGH | 130 | 130 (100%) | 0.824 | 1.0 |

### Metrics by order condition

Overall (TDC identical for all orders: **0.7655**; fulfilled 3,730,435; unmet
1,136,784; critical required 582,373; utilization 0.927):

| Condition | CDC mean | CDC pooled | Critical fulfilled | Critical unmet |
|---|---|---|---|---|
| FCFS | 0.7724 | 0.7686 | 447,640 | 134,733 |
| **AASHRAY** | **0.9876** | **0.9782** | **569,656** | **12,717** |
| REVERSE_FCFS | 0.7873 | 0.7848 | 457,036 | 125,337 |
| RANDOM_1 | 0.7538 | 0.7703 | 448,602 | 133,771 |
| RANDOM_2 | 0.7764 | 0.7786 | 453,419 | 128,954 |
| RANDOM_3 | 0.7423 | 0.7542 | 439,215 | 143,158 |

By scarcity (CDC mean over defined scenarios):

| Scarcity | TDC (all orders) | FCFS | AASHRAY | Reverse | Random 1/2/3 | Utilization |
|---|---|---|---|---|---|---|
| LOW | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 / 1.0000 / 1.0000 | 0.729 |
| MODERATE | 0.9786 | 0.9862 | 0.9998 | 0.9846 | 0.9735 / 0.9792 / 0.9643 | 0.973 |
| HIGH | 0.5042 | 0.5043 | 0.9727 | 0.5382 | 0.4709 / 0.5175 / 0.4512 | 1.000 |

Paired FCFS vs AASHRAY CDC (descriptive, not a hypothesis test): AASHRAY was
higher in 123 / 288 scenarios, lower in 0, and equal in 165. HIGH: 106 higher,
24 equal. MODERATE: 17 higher, 63 equal. LOW: all equal.

**Caveat on the AASHRAY CDC result.** With the provisional parameters,
P_o = 0.4S + 0.4U + 0.2√(SU) is almost a monotone transform of the reference
P_GT = 0.5S + 0.5U. An ad-hoc check (not part of the pilot outputs) gave
Spearman ρ(P_o, P_GT) = 0.995 over all emergencies. In all 287 scenarios that
mix critical and non-critical emergencies, AASHRAY ranked every GT-critical
emergency first. The CDC gain over FCFS is therefore largely expected by
construction under this GT rule. It confirms the harness works, not that the
formulation adds value beyond a simple S+U ordering.

---

## Validation

`results/validation_report.json`: **22 PASS, 0 FAIL, 0 SKIPPED**
(the 18 required checks, with check 14 split into 14a formula and 14b ranking,
plus C1 order honoured on every call, C2 same environment across orders, and
C3 fulfilment never exceeds supply or demand and matches the allocator's
reported shortage).

Determinism: regenerating the dataset twice gives byte-identical output, and an
in-memory rerun of the pilot is byte-identical to the files on disk.
Dataset sha256 `74995c508c0254d933685f0549fbc2e014f609112c4a69deb5535321c40d263b`
(generation config sha256 `2b377269…3639a`; the AASHRAY parameters are excluded
from it, so supplying them did not change the dataset).

## Limitations discovered

1. **No public order-controlled entry point.** `allocate()` does not share
   inventory between calls, and `allocate_batch()` imposes its own ranking.
   Order control relies on `allocate_batch` using a stable sort and on all
   placeholder scores tying. This is verified on every call but depends on that
   implementation detail.
2. **TDC is structurally order-invariant** for this allocator: greedy
   fulfilment, fungible stock, no compatibility, vehicle, distance or time
   constraints.
3. **TDC/CDC sum heterogeneous units.** Water (2/person) outweighs
   medical_kits (0.05/person) about 40×, so medical-kit shortages barely move
   the metrics.
4. **GT-critical demand is sparse.** 42% of scenarios have no GT-critical
   emergency, so CDC is undefined there. GT-critical emergencies come almost
   entirely from the HH stratum.
5. **The GT reference and the AASHRAY score are closely aligned** (see the
   caveat above). With P_GT = 0.5S + 0.5U as the CDC membership rule, CDC
   rewards any ranking that is nearly monotone in S + U.
6. The allocator ignores `vehicles` and warehouse location, so the scenarios
   carry no such constraints.

## Recommendation for the parameter-development experiment

These recommendations follow from the pilot; the methodology above is unchanged.

- Treat **TDC as descriptive**. It cannot discriminate between orderings
  under this allocator, so it should not be an optimization objective unless
  the allocator itself changes.
- Use **CDC as the primary order-sensitive objective**. Concentrate scenarios
  in **MODERATE and HIGH scarcity**: LOW scarcity produced zero variation in
  either metric.
- **Decide before tuning how to handle the P_GT / P_o alignment.** For
  example, add a naive `S+U` (or direct `P_GT`) ordering as a baseline, so any
  α/k/m/n configuration must beat a simple linear rule rather than FCFS only.
  Without that baseline, CDC will mostly favour configurations closest to
  0.5S + 0.5U.
- Raise the share of scenarios with **at least one GT-critical emergency**
  (e.g. require ≥ 1 by design or increase HH/MIXED weight), so fewer scenarios
  have undefined CDC.
- Consider reporting **per-resource-type CDC** (or unit-normalized demand)
  alongside the specified unit-summed CDC, so medical-kit coverage is visible.
- Keep the 2,000–3,000 development scenarios on a different master seed from
  this pilot and from the future 12,000 test set.
