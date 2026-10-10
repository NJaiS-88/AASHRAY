"""
threshold_calibration.py -- principled per-resource thresholds for JEV (no trial-and-error).

Pipeline per resource r:
  1. CALIBRATE   raw score -> probability (isotonic if enough positives, else Platt), cross-fitted.
  2. COST-OPTIMAL  Bayes threshold  tau_cost = C_FP / (C_FP + C_FN)   (valid because scores are now probabilities)
  3. GUARANTEE     Learn-then-Test: largest tau whose Clopper-Pearson UPPER bound on FNR <= alpha  (prob >= 1-delta)
  4. FINAL         tau_r = min(tau_cost, tau_guarantee); if too few positives -> back off to parent/group threshold.
"""
import numpy as np
from math import ceil, log
from scipy.stats import beta
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

def min_positives(alpha, delta):
    """Positives needed so that even ZERO observed misses certifies FNR<=alpha at confidence 1-delta."""
    return ceil(log(delta) / log(1 - alpha))

def ece(p, y, bins=10):
    idx = np.minimum((p * bins).astype(int), bins - 1); e = 0
    for b in range(bins):
        m = idx == b
        if m.any(): e += m.mean() * abs(p[m].mean() - y[m].mean())
    return e

def fit_calibrator(s, y, min_pos_isotonic=50):
    if y.sum() >= min_pos_isotonic:
        c = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(s, y); return c.predict, "isotonic"
    lg = LogisticRegression(C=1e6).fit(np.log(s / (1 - s + 1e-9) + 1e-9).reshape(-1, 1), y)
    return (lambda x: lg.predict_proba(np.log(x / (1 - x + 1e-9) + 1e-9).reshape(-1, 1))[:, 1]), "platt"

def cross_fit(s, y, k=5, seed=0):
    """Out-of-fold calibrated probabilities so calibration & threshold selection don't reuse the same rows."""
    out = np.zeros_like(s, float)
    for tr, te in StratifiedKFold(k, shuffle=True, random_state=seed).split(s, y):
        f, _ = fit_calibrator(s[tr], y[tr]); out[te] = f(s[te])
    return out

def bayes_threshold(c_fn, c_fp=1.0):
    return c_fp / (c_fp + c_fn)

def ltt_threshold(p, y, alpha=0.05, delta=0.10, grid=None):
    """Fixed-sequence Learn-then-Test over ascending tau (FNR is monotone in tau => no multiplicity penalty)."""
    grid = np.linspace(0.01, 0.90, 90) if grid is None else grid
    pos = p[y == 1]; n = len(pos); best = None
    for tau in grid:
        miss = int((pos < tau).sum())
        ub = beta.ppf(1 - delta, miss + 1, n - miss) if miss < n else 1.0   # Clopper-Pearson one-sided upper
        if ub <= alpha: best = tau
        else: break
    return best, n

def resource_threshold(s, y, c_fn, alpha=0.05, delta=0.10, parent_tau=None):
    n_pos = int(y.sum()); need = min_positives(alpha, delta)
    p = cross_fit(s, y); _, kind = fit_calibrator(s, y)
    tau_cost = bayes_threshold(c_fn)
    tau_g, _ = ltt_threshold(p, y, alpha, delta)
    status = "ok"
    if tau_g is None:                       # cannot certify even at the lowest tau
        status, tau = "UNCERTIFIED: lower bound unattainable", tau_cost
    elif n_pos < need:
        status = f"LOW-DATA: {n_pos}<{need} positives; guarantee is weak"
        tau = min(tau_cost, tau_g, parent_tau if parent_tau else 1)
    else: tau = min(tau_cost, tau_g)
    prec = (p[p >= tau] > 0).mean() if (p >= tau).any() else np.nan
    return dict(tau_cal=round(float(tau), 3), tau_cost=round(tau_cost, 3), tau_ltt=None if tau_g is None else round(float(tau_g), 3),
                n_pos=n_pos, n_needed=need, calibrator=kind, ece_before=round(ece(s, y), 3), ece_after=round(ece(p, y), 3),
                recall_at_tau=round(float((p[y == 1] >= tau).mean()), 3),
                flag_rate=round(float((p >= tau).mean()), 3), status=status)

def raw_threshold_from_calibrated(s, y, tau_cal):
    """Map calibrated tau back to the raw JEV score scale (what the API compares against)."""
    f, _ = fit_calibrator(s, y); g = np.linspace(0.001, 0.999, 999); pr = f(g)
    ok = np.where(pr >= tau_cal)[0]; return float(g[ok[0]]) if len(ok) else 1.0

# ---- cost tiers: ELICIT these from NDMA/SDMA domain experts (pairwise ranking), these are placeholders ----
COST_RATIO_C_FN = {"life_critical": 20, "health_critical": 10, "survival_basic": 6, "recovery": 3}
# tau_cost: 20->0.048, 10->0.091, 6->0.143, 3->0.25

if __name__ == "__main__":
    rng = np.random.default_rng(1)
    def synth(n, prev, sep):                 # compressed scores: well-ranked but systematically low
        y = (rng.random(n) < prev).astype(int)
        z = rng.normal(-3.0 + sep * y, 1.0); return 1 / (1 + np.exp(-z)), y
    print("min positives for alpha=.05,d=.10:", min_positives(.05, .10), "| alpha=.10:", min_positives(.10, .10))
    for name, prev, sep, tier in [("search_and_rescue", .15, 2.6, "life_critical"), ("fuel_cooking", .06, 1.5, "recovery")]:
        s, y = synth(3000, prev, sep); r = resource_threshold(s, y, COST_RATIO_C_FN[tier])
        st, yt = synth(20000, prev, sep)                         # fresh test set
        f, _ = fit_calibrator(s, y); pt = f(st)
        tr = raw_threshold_from_calibrated(s, y, r["tau_cal"])
        fnr = (pt[yt == 1] < r["tau_cal"]).mean()
        print(f"\n{name} ({tier})  mean raw score of positives={s[y==1].mean():.2f}  (looks 'low' but is rankable)")
        print({k: v for k, v in r.items()}); print(f"  raw-score cutoff to ship in API: {tr:.3f}   TEST FNR={fnr:.3f} (target<=0.05)")
        print(f"  old global 0.15 on raw scores -> TEST FNR={(st[yt==1] < 0.15).mean():.3f}")
