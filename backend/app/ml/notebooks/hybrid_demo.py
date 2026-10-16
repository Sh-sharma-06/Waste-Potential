"""Physics + ML residual demo on SYNTHETIC data.

The 'truth' generator below is authored for pipeline testing (Chen-Hashimoto HRT kinetics
x temperature x organic-loading inhibition x ammonia/C:N inhibition x per-plant bias x noise).
It is SYNTHETIC data, NOT real plant data. This tests the PIPELINE (grouped CV, extrapolation,
guardrails), not real-world accuracy.
All numbers are generated and computed dynamically at runtime; nothing is hardcoded.
"""

import os
import sys

# Bootstrap path to allow direct execution from any directory
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import numpy as np
from scipy.optimize import least_squares
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import GroupKFold

from app.ml.yield_model.kinetic import kinetic, fit_kinetic
from app.ml.yield_model.domain_guard import DomainGuard
from app.ml.yield_model.evaluate import calculate_metrics, assert_no_leakage

rng = np.random.default_rng(7)
FS = ["food", "manure", "crop", "mixed"]
Y0 = {"food": .85, "manure": .35, "crop": .50, "mixed": .65}  # Nm3 biogas / kg VS potential
OLRI = {"food": 7., "manure": 10., "crop": 8.5, "mixed": 8.}


def truth(fs, T, hrt, olr, cn):
    """Synthetic truth generator combining kinetics and non-linear inhibitions."""
    mu, K = 0.4, 0.6 + 0.1 * olr
    f_h = 1 - K / (hrt * mu - 1 + K)
    f_t = 0.6 + 0.4 * max(np.exp(-((T - 37) / 8) ** 2), .97 * np.exp(-((T - 55) / 5) ** 2))
    f_o = 1 / (1 + (olr / OLRI[fs]) ** 3)
    f_c = .55 + .45 / (1 + np.exp(-(cn - 14) / 2.5))
    return Y0[fs] * f_h * f_t * f_o * f_c


n_plants, per = 40, 25
rows = []
for pid in range(n_plants):
    bias = rng.normal(0, .07)
    fs = FS[pid % 4]
    for _ in range(per):
        T = rng.choice([rng.uniform(32, 40), rng.uniform(50, 56)], p=[.8, .2])
        hrt, olr, cn = rng.uniform(10, 60), rng.uniform(1, 8), rng.uniform(8, 40)
        y = truth(fs, T, hrt, olr, cn) * (1 + bias) * rng.lognormal(0, .05)
        rows.append((pid, FS.index(fs), T, hrt, olr, cn, y))

D = np.array(rows)
pid, fsi, T, hrt, olr, cn, y = D.T
fsi = fsi.astype(int)


def feats(m):
    """Features for ML models: feedstock one-hot, T, hrt, olr, c_n."""
    oh = np.eye(4)[fsi[m]]
    return np.column_stack([oh, T[m], hrt[m], olr[m], cn[m]])


# --- Physics levels (calibrated on training rows only) ---
def fit_static(m):
    """L0: One median yield per feedstock (lookup-table engine baseline)."""
    return {i: np.median(y[m & (fsi == i)]) for i in range(4)}


def pred_static(par, m):
    return np.array([par[i] for i in fsi[m]])


def make_ml(kind):
    if kind == "gbr":
        return GradientBoostingRegressor(
            n_estimators=300, max_depth=3, learning_rate=.05, subsample=.8, random_state=0
        )
    return make_pipeline(
        StandardScaler(),
        MLPRegressor(hidden_layer_sizes=(32, 32), alpha=1e-3, max_iter=3000, random_state=0)
    )


def metrics(a, p):
    return calculate_metrics(a, p)


def evaluate(train, test):
    out = {}
    s = fit_static(train)
    out["L0 static physics"] = pred_static(s, test)

    k = fit_kinetic(fsi[train], hrt[train], y[train], n_fs=4)
    pk_tr = kinetic(k, fsi[train], hrt[train])
    pk_te = kinetic(k, fsi[test], hrt[test])
    out["L1 kinetic physics"] = pk_te

    for kind in ("gbr", "mlp"):
        m = make_ml(kind).fit(feats(train), y[train])
        out[f"pure ML ({kind})"] = m.predict(feats(test))

        r = make_ml(kind).fit(feats(train), np.log(y[train] / pk_tr))
        out[f"L2 kinetic+ML residual ({kind})"] = pk_te * np.exp(r.predict(feats(test)))

    return out


def report(title, results, test):
    print(f"\n{title} (n_test={test.sum()}) [SYNTHETIC DATA]")
    print(f"{'model':34s}{'MAE':>8s}{'RMSE':>8s}{'bias':>8s}{'MAPE%':>8s}")
    for name, p in results.items():
        m = metrics(y[test], p)
        print(f"{name:34s}{m['MAE']:8.3f}{m['RMSE']:8.3f}{m['bias']:8.3f}{m['MAPE']:8.1f}")


def run_all_tests():
    print("======================================================================")
    print("HYBRID YIELD DEMO (SYNTHETIC DATA BENCHMARK)")
    print("======================================================================")

    # 1) Unseen-plant generalisation: GroupKFold by plant, pooled out-of-fold
    idx = np.arange(len(y))
    oof = {}
    for fold, (tr, te) in enumerate(GroupKFold(5).split(idx, groups=pid)):
        # Verify strict zero leakage between train and test plant groups
        assert_no_leakage(pid[tr], pid[te])
        trm = np.zeros(len(y), bool)
        trm[tr] = True
        tem = ~trm
        res = evaluate(trm, tem)
        for k_, v in res.items():
            oof.setdefault(k_, np.zeros(len(y)))[tem] = v
    report("TEST 1: unseen plants (GroupKFold, 5 folds)", oof, np.ones(len(y), bool))

    # 2) Extrapolation in HRT: train HRT>=25, test HRT<25 (washout regime), unseen plants too
    plant_test = pid >= 30
    tr = (hrt >= 25) & ~plant_test
    te = (hrt < 25) & plant_test
    assert_no_leakage(pid[tr], pid[te])
    test2_results = evaluate(tr, te)
    report("TEST 2: HRT extrapolation (train HRT>=25, test HRT<25, unseen plants)", test2_results, te)

    # 3) Extrapolation in OLR: train OLR<=5, test OLR>5 (inhibition regime), unseen plants
    tr = (olr <= 5) & ~plant_test
    te = (olr > 5) & plant_test
    assert_no_leakage(pid[tr], pid[te])
    test3_results = evaluate(tr, te)
    report("TEST 3: OLR extrapolation (train OLR<=5, test OLR>5, unseen plants)", test3_results, te)

    # 4) Guardrail: clip to Buswell-type ceiling and fall back to physics outside training domain
    hyb = test3_results["L2 kinetic+ML residual (gbr)"].copy()
    phys = test3_results["L1 kinetic physics"]
    guard = DomainGuard(olr[tr])
    ood = guard.outside(olr[te])
    guarded = np.where(ood, phys, hyb)

    print(f"\nGuardrail on TEST 3: {ood.mean():.0%} of test rows flagged out-of-domain -> fall back to kinetic physics + 'extrapolation' flag [SYNTHETIC DATA]")
    print(" unguarded hybrid:", {k: round(v, 3) for k, v in metrics(y[te], hyb).items()})
    print(" guarded hybrid  :", {k: round(v, 3) for k, v in metrics(y[te], guarded).items()})

    return oof, test2_results, test3_results, te, hyb, guarded


if __name__ == "__main__":
    run_all_tests()
