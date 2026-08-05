"""Does the invented-exact-CPV anomaly affect algorithm selection?

Exact CPV codes are not used by blocking (blocking = buyer_key + time window).
They enter only through the s_cpv feature. This ablation degrades s_cpv to the
information that IS faithful -- the division-level match -- and checks whether
the algorithm ranking changes. If ranking is unchanged, the anomaly is a
documented fidelity limitation, not a threat to algorithm comparison.
"""
from __future__ import annotations
import sys, warnings
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
from sklearn.metrics import precision_recall_fscore_support

VERSION = 'v0_4_population_alias_revision'

cfg = load_config(ROOT); P = cfg.pipeline
NUM = ['s_text', 's_cpv', 's_time', 's_buyer', 'gap_months',
       'abs_gap_to_expected_end', 'n_candidates_for_source']
BIN = ['cpv_missing', 'cpv_generic_flag']; CAT = ['buyer_key_type']
FEATS = NUM + BIN + CAT
EVAL = [(s, w) for s in ['central_provisional', 'easier', 'difficult', 'stress']
        for w in ['007', '008', '009', '010']]

def load(scen, w):
    d = load_benchmark_data(ROOT, VERSION, scen, w, w)
    sc = scoped_sources(d); ids = set(sc['notice_id'].astype(str))
    tr = true_match_pairs(d)
    tin = tr.loc[tr['notice_a'].astype(str).isin(ids) & tr['notice_b'].astype(str).isin(ids)]
    ts = {_unordered(a, b) for a, b in zip(tin['notice_a'], tin['notice_b'])}
    p, _ = generate_pairs_single_key(sc, cfg, verbose=False)
    p['is_true_match'] = [_unordered(a, b) in ts for a, b in
                          zip(p['source_notice_id'], p['candidate_notice_id'])]
    p['scenario'], p['world'] = scen, w
    p['n_truth'] = len(ts)
    p['n_reach'] = len({_unordered(a, b) for a, b in
                        zip(p['source_notice_id'], p['candidate_notice_id'])} & ts)
    return p

print('loading...', flush=True)
fit = pd.concat([load('central_provisional', w) for w in ['001', '002', '003', '004']])
cal = pd.concat([load('central_provisional', w) for w in ['005', '006']])
ev = pd.concat([load(s, w) for s, w in EVAL])
print(f'fit {len(fit)} cal {len(cal)} eval {len(ev)}', flush=True)

def degrade(df):
    """Keep only division-level CPV information (the part that is faithful)."""
    d = df.copy()
    d['s_cpv'] = np.where(d['s_cpv'] >= 0.2, 0.2, d['s_cpv'])
    return d

def prep(df):
    x = df.reindex(columns=FEATS).copy()
    for c in BIN: x[c] = pd.to_numeric(x[c], errors='coerce').astype(float)
    x[CAT[0]] = x[CAT[0]].astype(str)
    return x

def run(tag, f, c, e):
    pre_lr = ColumnTransformer([('n', Pipeline([('i', SimpleImputer(strategy='median')),
                                                ('s', StandardScaler())]), NUM + BIN),
                                ('c', OneHotEncoder(handle_unknown='ignore'), CAT)])
    pre_gb = ColumnTransformer([('n', SimpleImputer(strategy='median'), NUM + BIN),
                                ('c', OneHotEncoder(handle_unknown='ignore'), CAT)])
    mods = {'gradient_boosting': Pipeline([('p', pre_gb),
                ('m', HistGradientBoostingClassifier(random_state=20260713))]),
            'logistic_regression': Pipeline([('p', pre_lr),
                ('m', LogisticRegression(max_iter=2000))])}
    out = []
    for nm, m in mods.items():
        m.fit(prep(f), f['is_true_match'].astype(int))
        cp = m.predict_proba(prep(c))[:, 1]
        bt, bf = .5, -1
        for t in np.quantile(cp, np.linspace(.5, .9995, 100)):
            _, _, f1, _ = precision_recall_fscore_support(
                c['is_true_match'].astype(int), (cp >= t).astype(int),
                average='binary', zero_division=0)
            if f1 > bf: bf, bt = f1, t
        pr = m.predict_proba(prep(e))[:, 1] >= bt
        g = e.assign(pred=pr)
        for (sc, w), gg in g.groupby(['scenario', 'world']):
            tp = int((gg.pred & gg.is_true_match).sum()); npd = int(gg.pred.sum())
            prec = tp / npd if npd else 0
            rece = tp / gg['n_truth'].iloc[0]
            out.append(dict(ablation=tag, algorithm=nm, scenario=sc, world=w,
                            precision=prec, recall_end_to_end=rece,
                            f1_end_to_end=2 * prec * rece / (prec + rece) if prec + rece else 0))
    # transparent baseline
    for (sc, w), gg in e.groupby(['scenario', 'world']):
        pr = (gg['composite_score'] >= P.thresholds.balanced) & (gg['candidate_rank'] == 1)
        tp = int((pr & gg.is_true_match).sum()); npd = int(pr.sum())
        prec = tp / npd if npd else 0; rece = tp / gg['n_truth'].iloc[0]
        out.append(dict(ablation=tag, algorithm='current_weighted_composite', scenario=sc,
                        world=w, precision=prec, recall_end_to_end=rece,
                        f1_end_to_end=2 * prec * rece / (prec + rece) if prec + rece else 0))
    return pd.DataFrame(out)

res = pd.concat([run('full_cpv_ladder', fit, cal, ev),
                 run('division_only_cpv', degrade(fit), degrade(cal), degrade(ev))])
res.to_csv(OUT / 'cpv_anomaly_ablation.csv', index=False)
s = res.groupby(['ablation', 'algorithm'])[['precision', 'recall_end_to_end', 'f1_end_to_end']].mean()
print('\n' + s.round(4).to_string())
print('\nrank-1 frequency by ablation (16 unique eval worlds):')
for ab, g in res.groupby('ablation'):
    rk = g.pivot_table(index=['scenario', 'world'], columns='algorithm', values='f1_end_to_end')
    print(f'  {ab}: {dict(rk.idxmax(axis=1).value_counts())}')
