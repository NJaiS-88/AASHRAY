"""Pre-registered statistical procedures for the final hypothesis test.

All randomness uses numpy.random.default_rng (PCG64) with the documented
seed; the chunk sizes below are part of the procedure (they fix how the
random stream is consumed), so re-running reproduces results exactly.
"""

import math

import numpy as np
from scipy.stats import wilcoxon


PERMUTATION_CHUNK = 1000
BOOTSTRAP_CHUNK = 500


def permutation_test(delta: np.ndarray, permutations: int, seed: int) -> dict:
    """One-sided paired sign-flip randomization test of H1: mean(delta) > 0.

    Under H0 each difference is equally likely to have either sign, so every
    sign assignment is equally likely. p = (1 + #{permuted mean >= observed
    mean}) / (permutations + 1).
    """

    n = delta.size
    observed = float(delta.mean())
    rng = np.random.default_rng(seed)
    at_least_as_extreme = 0

    for start in range(0, permutations, PERMUTATION_CHUNK):
        size = min(PERMUTATION_CHUNK, permutations - start)
        signs = rng.integers(0, 2, size=(size, n), dtype=np.int8).astype(np.float64) * 2.0 - 1.0
        means = signs @ delta / n
        at_least_as_extreme += int(np.count_nonzero(means >= observed))

    return {
        "test_name": "one-sided paired sign-flip permutation (randomization) test",
        "alternative": "greater: mean(CDC_AASHRAY - CDC_FCFS) > 0",
        "statistic_name": "mean paired difference",
        "statistic": observed,
        "n": int(n),
        "permutations": permutations,
        "seed": seed,
        "rng": "numpy.random.default_rng (PCG64)",
        "chunk_size": PERMUTATION_CHUNK,
        "permuted_means_at_least_observed": at_least_as_extreme,
        "p_value": (1 + at_least_as_extreme) / (permutations + 1),
        "p_value_formula": "(1 + count) / (permutations + 1)",
        "smallest_attainable_p_value": 1 / (permutations + 1),
    }


def bootstrap_ci(delta: np.ndarray, resamples: int, seed: int, level: float) -> dict:
    """Paired percentile bootstrap of mean(delta): scenarios (pairs) are
    resampled with replacement, so the pairing is preserved."""

    n = delta.size
    rng = np.random.default_rng(seed)
    means = np.empty(resamples)

    for start in range(0, resamples, BOOTSTRAP_CHUNK):
        size = min(BOOTSTRAP_CHUNK, resamples - start)
        index = rng.integers(0, n, size=(size, n))
        means[start:start + size] = delta[index].mean(axis=1)

    tail = (1 - level) / 2 * 100
    lower, upper = np.percentile(means, [tail, 100 - tail])

    return {
        "test_name": "paired percentile bootstrap confidence interval for mean(CDC_AASHRAY - CDC_FCFS)",
        "n": int(n),
        "resamples": resamples,
        "seed": seed,
        "rng": "numpy.random.default_rng (PCG64)",
        "chunk_size": BOOTSTRAP_CHUNK,
        "level": level,
        "percentiles": [tail, 100 - tail],
        "percentile_method": "numpy.percentile, linear interpolation",
        "estimate": float(delta.mean()),
        "confidence_interval": [float(lower), float(upper)],
        "bootstrap_mean_of_means": float(means.mean()),
        "bootstrap_standard_error": float(means.std(ddof=1)),
    }


def wilcoxon_test(delta: np.ndarray, tie_tolerance: float) -> dict:
    """One-sided paired Wilcoxon signed-rank test; zero differences dropped."""

    nonzero = int(np.count_nonzero(delta))
    exact_zero = int(delta.size - nonzero)
    result = wilcoxon(delta, zero_method="wilcox", alternative="greater",
                      method="approx", correction=False)

    return {
        "test_name": "one-sided paired Wilcoxon signed-rank test (secondary)",
        "alternative": "greater: CDC_AASHRAY > CDC_FCFS",
        "implementation": "scipy.stats.wilcoxon(delta, zero_method='wilcox', alternative='greater', method='approx', correction=False)",
        "zero_method": "wilcox: zero differences are dropped from the ranking and counted separately",
        "method": "normal approximation (n is large); tied absolute differences get average ranks",
        "statistic_name": "sum of ranks of positive differences (W+)",
        "statistic": float(result.statistic),
        "p_value": float(result.pvalue),
        "n": int(delta.size),
        "n_nonzero_differences": nonzero,
        "n_zero_differences": exact_zero,
        "n_differences_within_tie_tolerance": int(np.count_nonzero(np.abs(delta) <= tie_tolerance)),
    }


def effect_sizes(delta: np.ndarray, tie_tolerance: float) -> dict:
    n = delta.size
    sd = float(delta.std(ddof=1)) if n > 1 else math.nan
    wins = int(np.count_nonzero(delta > tie_tolerance))
    losses = int(np.count_nonzero(delta < -tie_tolerance))
    ties = int(n - wins - losses)

    return {
        "test_name": "paired effect sizes",
        "n": int(n),
        "mean_difference": float(delta.mean()),
        "median_difference": float(np.median(delta)),
        "sd_difference": sd,
        "cohens_dz": float(delta.mean()) / sd if sd and sd > 0 else math.nan,
        "cohens_dz_definition": "mean(delta) / sample SD(delta), ddof = 1; NaN if SD = 0",
        "aashray_wins": wins,
        "ties": ties,
        "fcfs_wins": losses,
        "win_rate": wins / n,
        "tie_rate": ties / n,
        "fcfs_win_rate": losses / n,
        "probability_of_superiority": (wins + 0.5 * ties) / n,
        "probability_of_superiority_definition": "(AASHRAY wins + 0.5 * ties) / n, paired by scenario",
        "tie_tolerance": tie_tolerance,
    }
