"""Bounded candidate-generator sensitivity on the v0.4 synthetic benchmark.

Variant family is taken from the repository's own documented methodology:
  G1 dur_w6   duration-anchored +/-6m   -- canonical (config/pipeline.yaml temporal_window)
  G2 dur_w12  duration-anchored +/-12m  -- config/pipeline.yaml sensitivity_windows_months
  G3 dur_w18  duration-anchored +/-18m  -- config/pipeline.yaml sensitivity_windows_months
  G4 fwd24    forward 24m, no duration  -- config/pipeline.yaml evaluation.duration_leakage_forward_months
                                           implemented by boamp.validation.linkage_quality.forward_pairs

No parameter here is chosen using hidden truth.

Split (unchanged, by world): fit = central 001-004, calibration = central 005-006,
evaluation = worlds 007-010 of each UNIQUE scenario (moderate excluded as a
verified byte-identical duplicate of central_provisional).
"""
from __future__ import annotations

import json, time, sys, warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
ROOT = Path('/home/senghakrou/survival-analysis')
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'reports/tables/real_linkage_freeze'

from boamp.config import load_config
from boamp.synthetic.validation_framework.loaders import load_benchmark_data
from boamp.synthetic.validation_framework.difficulty import (
    scoped_sources, true_match_pairs, _unordered)
from boamp.linkage.candidates import generate_pairs_single_key
from boamp.linkage.scoring import build_tfidf_matrix
from boamp.validation.linkage_quality import forward_pairs

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.metrics import precision_recall_fscore_support

VERSION = 'v0_4_population_alias_revision'
cfg = load_config(ROOT)
FIT = [('central_provisional', w) for w in ['001', '002', '003', '004']]
CAL = [('central_provisional', w) for w in ['005', '006']]
UNIQUE_EVAL_SCENARIOS = ['central_provisional', 'easier', 'difficult', 'stress']
EVAL = [(s, w) for s in UNIQUE_EVAL_SCENARIOS for w in ['007', '008', '009', '010']]

VARIANTS = ['dur_w6', 'dur_w12', 'dur_w18', 'fwd24']

NUM = ['s_text', 's_cpv', 's_time', 's_buyer', 'gap_months',
       'abs_gap_to_expected_end', 'n_candidates_for_source']
BIN = ['cpv_missing', 'cpv_generic_flag']
CAT = ['buyer_key_type']
FEATS = NUM + BIN + CAT


def build_pairs(variant, scoped):
    t0 = time.time()
    if variant.startswith('dur_w'):
        w = int(variant.replace('dur_w', ''))
        pairs, _ = generate_pairs_single_key(scoped, cfg, verbose=False, window_override=w)
    else:
        months = int(variant.replace('fwd', ''))
        eligible = scoped[scoped['buyer_key_type'] != 'MISSING'].copy()
        eligible = eligible.sort_values(['buyer_key', 'publication_date']).reset_index(drop=True)
        _v, tfidf = build_tfidf_matrix(eligible['objet_clean'].fillna('').tolist(), cfg)
        pairs = forward_pairs(eligible, tfidf, cfg, months=months)
    return pairs, time.time() - t0


def world_frame(variant, scenario, world):
    data = load_benchmark_data(ROOT, VERSION, scenario, world, world)
    scoped = scoped_sources(data)
    ids = set(scoped['notice_id'].astype(str))
    truth = true_match_pairs(data)
    tin = truth.loc[truth['notice_a'].astype(str).isin(ids)
                    & truth['notice_b'].astype(str).isin(ids)]
    truth_set = {_unordered(a, b) for a, b in zip(tin['notice_a'], tin['notice_b'])}

    pairs, secs = build_pairs(variant, scoped)
    if not len(pairs):
        return None
    pairs = pairs.copy()
    pairs['is_true_match'] = [_unordered(a, b) in truth_set for a, b in
                              zip(pairs['source_notice_id'], pairs['candidate_notice_id'])]
    cand_set = {_unordered(a, b) for a, b in
                zip(pairs['source_notice_id'], pairs['candidate_notice_id'])}
    reachable = len(cand_set & truth_set)

    ncand = pairs.groupby('source_notice_id').size()
    maxc = cfg.pipeline.candidates.max_candidates_per_source
    meta = dict(
        variant=variant, scenario=scenario, world=world,
        n_scoped=len(scoped), n_pairs=len(pairs),
        n_truth_in_scope=len(truth_set), n_reachable=reachable,
        blocking_recall=reachable / len(truth_set) if truth_set else np.nan,
        cand_median=float(ncand.median()), cand_q90=float(ncand.quantile(.9)),
        cand_q99=float(ncand.quantile(.99)),
        cap_rate=float((ncand >= maxc).mean()), seconds=secs)
    for c in FEATS:
        if c not in pairs.columns:
            pairs[c] = np.nan
    pairs['scenario'] = scenario
    pairs['world'] = world
    return pairs[FEATS + ['is_true_match', 'scenario', 'world', 'source_notice_id',
                          'candidate_notice_id', 'composite_score', 'candidate_rank']], meta


def make_models():
    pre = ColumnTransformer([
        ('num', Pipeline([('imp', SimpleImputer(strategy='median')),
                          ('sc', StandardScaler())]), NUM + BIN),
        ('cat', OneHotEncoder(handle_unknown='ignore'), CAT)])
    return {
        'logistic_regression': Pipeline([('pre', pre),
                                         ('m', LogisticRegression(max_iter=2000, C=1.0))]),
        'gradient_boosting': Pipeline([
            ('pre', ColumnTransformer([
                ('num', SimpleImputer(strategy='median'), NUM + BIN),
                ('cat', OneHotEncoder(handle_unknown='ignore'), CAT)])),
            ('m', HistGradientBoostingClassifier(random_state=20260713))]),
    }


def prep(df):
    x = df[FEATS].copy()
    for c in BIN:
        x[c] = pd.to_numeric(x[c], errors='coerce').astype(float)
    x[CAT[0]] = x[CAT[0]].astype(str)
    return x


results, metas = [], []
for variant in VARIANTS:
    print(f'\n===== {variant} =====', flush=True)
    fit_f, cal_f, ev_f = [], [], []
    for scen, w in FIT:
        r = world_frame(variant, scen, w)
        if r: fit_f.append(r[0]); metas.append(r[1]); print('  fit', w, r[1]['n_pairs'], f"{r[1]['blocking_recall']:.3f}", flush=True)
    for scen, w in CAL:
        r = world_frame(variant, scen, w)
        if r: cal_f.append(r[0]); metas.append(r[1]); print('  cal', w, r[1]['n_pairs'], f"{r[1]['blocking_recall']:.3f}", flush=True)
    for scen, w in EVAL:
        r = world_frame(variant, scen, w)
        if r: ev_f.append(r[0]); metas.append(r[1]); print('  ev ', scen, w, r[1]['n_pairs'], f"{r[1]['blocking_recall']:.3f}", flush=True)

    fit_df, cal_df, ev_df = pd.concat(fit_f), pd.concat(cal_f), pd.concat(ev_f)
    models = make_models()
    scores = {}
    for name, mdl in models.items():
        mdl.fit(prep(fit_df), fit_df['is_true_match'].astype(int))
        cal_p = mdl.predict_proba(prep(cal_df))[:, 1]
        # threshold by F1 maximisation on the calibration worlds only
        best_t, best_f1 = 0.5, -1
        for t in np.quantile(cal_p, np.linspace(0.5, 0.9995, 120)):
            pr, rc, f1, _ = precision_recall_fscore_support(
                cal_df['is_true_match'].astype(int), (cal_p >= t).astype(int),
                average='binary', zero_division=0)
            if f1 > best_f1: best_f1, best_t = f1, t
        scores[name] = (mdl, best_t)

    # frozen transparent baseline: composite score at the frozen balanced threshold
    thr_comp = cfg.pipeline.thresholds.balanced

    for name, (mdl, t) in list(scores.items()) + [('current_weighted_composite', (None, thr_comp))]:
        if mdl is None:
            pred = (ev_df['composite_score'] >= t) & (ev_df['candidate_rank'] == 1)
        else:
            pred = mdl.predict_proba(prep(ev_df))[:, 1] >= t
        ev = ev_df.assign(pred=pred.astype(bool))
        for (scen, w), g in ev.groupby(['scenario', 'world']):
            m = [x for x in metas if x['variant'] == variant and x['scenario'] == scen and x['world'] == w][0]
            tp = int((g.pred & g.is_true_match).sum())
            npred = int(g.pred.sum())
            results.append(dict(
                variant=variant, algorithm=name, scenario=scen, world=w,
                n_pairs=len(g), n_truth=m['n_truth_in_scope'], n_reachable=m['n_reachable'],
                blocking_recall=m['blocking_recall'], n_pred=npred, tp=tp,
                precision=tp / npred if npred else 0.0,
                recall_conditional=tp / m['n_reachable'] if m['n_reachable'] else np.nan,
                recall_end_to_end=tp / m['n_truth_in_scope'] if m['n_truth_in_scope'] else np.nan,
                threshold=float(t)))
        print(f'  [{name}] done', flush=True)

res = pd.DataFrame(results)
for c, a, b in [('f1_conditional', 'precision', 'recall_conditional'),
                ('f1_end_to_end', 'precision', 'recall_end_to_end')]:
    res[c] = 2 * res[a] * res[b] / (res[a] + res[b]).replace(0, np.nan)
res.to_csv(OUT / 'gen_sensitivity_results.csv', index=False)
pd.DataFrame(metas).to_csv(OUT / 'gen_sensitivity_meta.csv', index=False)
print('\nWROTE', OUT / 'gen_sensitivity_results.csv')
