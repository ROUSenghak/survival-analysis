"""Can a synthetic-trained supervised linker be applied to real BOAMP?

Trains GBM + logistic regression on the synthetic fit worlds under the canonical
candidate generator, then compares the feature and score distributions between
the synthetic calibration worlds and the real Layer-1 candidate pairs.
The real corpus has no labels, so this can only test transferability of the
input distribution and the implied decision volume -- never real precision/recall.
"""
from __future__ import annotations
import sys, warnings, json
from pathlib import Path
import numpy as np, pandas as pd

warnings.filterwarnings('ignore')
ROOT = Path('/home/senghakrou/survival-analysis')
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'reports/tables/real_linkage_freeze'

from boamp.config import load_config
from boamp.synthetic.validation_framework.loaders import load_benchmark_data
from boamp.synthetic.validation_framework.difficulty import (
    scoped_sources, true_match_pairs, _unordered)
from boamp.linkage.candidates import generate_pairs_single_key
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

cfg = load_config(ROOT); P = cfg.pipeline
NUM = ['s_text', 's_cpv', 's_time', 's_buyer', 'gap_months',
       'abs_gap_to_expected_end', 'n_candidates_for_source']
BIN = ['cpv_missing', 'cpv_generic_flag']
CAT = ['buyer_key_type']
FEATS = NUM + BIN + CAT

def load_syn(world):
    data = load_benchmark_data(ROOT, 'v0_4_population_alias_revision',
                               'central_provisional', world, world)
    scoped = scoped_sources(data)
    ids = set(scoped['notice_id'].astype(str))
    tr = true_match_pairs(data)
    tin = tr.loc[tr['notice_a'].astype(str).isin(ids) & tr['notice_b'].astype(str).isin(ids)]
    ts = {_unordered(a, b) for a, b in zip(tin['notice_a'], tin['notice_b'])}
    pairs, _ = generate_pairs_single_key(scoped, cfg, verbose=False)
    pairs['is_true_match'] = [_unordered(a, b) in ts for a, b in
                              zip(pairs['source_notice_id'], pairs['candidate_notice_id'])]
    return pairs

fit = pd.concat([load_syn(w) for w in ['001', '002', '003', '004']], ignore_index=True)
cal = pd.concat([load_syn(w) for w in ['005', '006']], ignore_index=True)
real = pd.read_csv(OUT / 'real_candidate_pairs_reproduced.csv')
print(f'synthetic fit pairs {len(fit)}, calibration {len(cal)}, real pairs {len(real)}')

def prep(df):
    x = df.reindex(columns=FEATS).copy()
    for c in BIN:
        x[c] = pd.to_numeric(x[c], errors='coerce').astype(float)
    x[CAT[0]] = x[CAT[0]].astype(str)
    return x

pre_lr = ColumnTransformer([('num', Pipeline([('i', SimpleImputer(strategy='median')),
                                              ('s', StandardScaler())]), NUM + BIN),
                            ('cat', OneHotEncoder(handle_unknown='ignore'), CAT)])
pre_gb = ColumnTransformer([('num', SimpleImputer(strategy='median'), NUM + BIN),
                            ('cat', OneHotEncoder(handle_unknown='ignore'), CAT)])
models = {
    'gradient_boosting': Pipeline([('p', pre_gb),
                                   ('m', HistGradientBoostingClassifier(random_state=20260713))]),
    'logistic_regression': Pipeline([('p', pre_lr),
                                     ('m', LogisticRegression(max_iter=2000))]),
}

rows = []
for nm, mdl in models.items():
    mdl.fit(prep(fit), fit['is_true_match'].astype(int))
    cal_p = mdl.predict_proba(prep(cal))[:, 1]
    # threshold at synthetic calibration F1 maximum
    from sklearn.metrics import precision_recall_fscore_support
    best_t, best_f1 = .5, -1
    for t in np.quantile(cal_p, np.linspace(.5, .9995, 120)):
        _, _, f1, _ = precision_recall_fscore_support(
            cal['is_true_match'].astype(int), (cal_p >= t).astype(int),
            average='binary', zero_division=0)
        if f1 > best_f1: best_f1, best_t = f1, t
    real_p = mdl.predict_proba(prep(real))[:, 1]
    n_src = real['source_notice_id'].nunique()
    r1 = real['candidate_rank'] == 1
    rows.append(dict(
        model=nm, synthetic_threshold=float(best_t), synthetic_cal_f1=float(best_f1),
        syn_cal_score_p50=float(np.median(cal_p)), syn_cal_score_p90=float(np.quantile(cal_p, .9)),
        real_score_p50=float(np.median(real_p)), real_score_p90=float(np.quantile(real_p, .9)),
        real_pairs_above_threshold=int((real_p >= best_t).sum()),
        real_rank1_above_threshold=int(((real_p >= best_t) & r1).sum()),
        implied_real_link_rate=float(((real_p >= best_t) & r1).sum() / 3380),
        syn_cal_positive_rate=float((cal_p >= best_t).mean()),
        real_positive_rate=float((real_p >= best_t).mean())))
    print(f'{nm}: syn thr={best_t:.4f} -> real rank-1 accepts='
          f'{int(((real_p>=best_t)&r1).sum())} (link rate '
          f'{((real_p>=best_t)&r1).sum()/3380:.4f})', flush=True)

tr = pd.DataFrame(rows)
tr.to_csv(OUT / 'synthetic_to_real_transfer_test.csv', index=False)

# feature-level covariate shift
sh = []
for c in ['s_text', 's_cpv', 's_time', 's_buyer', 'gap_months', 'n_candidates_for_source']:
    s, r = pd.to_numeric(cal[c], errors='coerce').dropna(), pd.to_numeric(real[c], errors='coerce').dropna()
    sh.append(dict(feature=c, syn_mean=float(s.mean()), real_mean=float(r.mean()),
                   syn_p50=float(s.median()), real_p50=float(r.median()),
                   syn_p90=float(s.quantile(.9)), real_p90=float(r.quantile(.9)),
                   ratio_of_means=float(s.mean() / r.mean()) if r.mean() else np.nan))
shift = pd.DataFrame(sh)
shift.to_csv(OUT / 'synthetic_vs_real_feature_shift.csv', index=False)
print('\n' + shift.to_string(index=False))
print('\n' + tr.to_string(index=False))
