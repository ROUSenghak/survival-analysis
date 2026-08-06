"""Can synthetic-trained supervised linkers be applied to real BOAMP?

This is a transfer stress test, not a real-accuracy estimate. It mirrors the
v0.4 benchmark model specification: train on central worlds 001-004, tune/record
rank-1 acceptance thresholds on worlds 005-006, score the real Layer-1 candidate
pairs, and export GBM-primary, logistic-sensitivity and strategy artifacts.

The real corpus has no labels, so the outputs below support only distribution
shift, implied decision volume, method agreement, and downstream survival
sensitivity. They never establish real precision or recall.
"""
from __future__ import annotations
import json, subprocess, sys, warnings
from pathlib import Path
import numpy as np, pandas as pd

warnings.filterwarnings('ignore')
ROOT = Path('/home/senghakrou/survival-analysis')
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'reports/tables/real_linkage_freeze'

from boamp.config import load_config
from boamp.synthetic.validation_framework.loaders import load_benchmark_data
from boamp.synthetic.validation_framework.difficulty import (
    FS_AGREEMENT_THRESHOLDS, FS_M_PROBABILITIES, FS_U_PROBABILITIES,
    _generate_candidates, _pair_key_set, _pair_scores, scoped_sources,
    true_match_pairs)
from boamp.linkage.links import assign_confidence_tier
from boamp.survival.datasets import build_survival_dataset
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_fscore_support
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from lifelines import KaplanMeierFitter
from lifelines.utils import restricted_mean_survival_time

cfg = load_config(ROOT); P = cfg.pipeline
VERSION = 'v0_4_population_alias_revision'
RANDOM_SEED = int(P.run.random_seed)
NUM = ['s_text', 's_cpv', 's_time', 's_buyer', 'gap_months',
       'abs_gap_to_expected_end', 'n_candidates_for_source',
       'source_publication_year']
BIN = ['cpv_missing', 'cpv_generic_flag', 'source_cpv_missing',
       'source_duration_missing']
CAT = ['buyer_key_type', 'source_schema_family', 'source_cpv_division']
FEATS = NUM + BIN + CAT


def git_value(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ['git', *args],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def add_source_candidate_context(scored: pd.DataFrame, scoped: pd.DataFrame) -> pd.DataFrame:
    attrs = scoped.copy()
    attrs['notice_id'] = attrs['notice_id'].astype(str)
    attrs['publication_year'] = pd.to_datetime(attrs['publication_date']).dt.year
    context_cols = [
        'notice_id', 'schema_family', 'notice_type_normalized',
        'publication_year', 'buyer_key_type', 'code_departement',
        'cpv_clean', 'cpv_division', 'declared_duration_months',
        'dur_was_imputed',
    ]
    available = [c for c in context_cols if c in attrs.columns]
    source_context = attrs[available].rename(
        columns={c: f'source_{c}' for c in available if c != 'notice_id'})
    candidate_context = attrs[available].rename(
        columns={c: f'candidate_{c}' for c in available if c != 'notice_id'})
    out = scored.merge(source_context, left_on='source_notice_id',
                       right_on='notice_id', how='left')
    out = out.drop(columns=['notice_id'], errors='ignore')
    out = out.merge(candidate_context, left_on='candidate_notice_id',
                    right_on='notice_id', how='left')
    out = out.drop(columns=['notice_id'], errors='ignore')
    out['source_cpv_missing'] = out['source_cpv_clean'].isna()
    out['source_duration_missing'] = out['source_declared_duration_months'].isna()
    return out


def fellegi_sunter_log_odds(frame: pd.DataFrame) -> pd.Series:
    score = np.zeros(len(frame), dtype=float)
    for field, threshold in FS_AGREEMENT_THRESHOLDS.items():
        values = pd.to_numeric(frame[field], errors='coerce')
        agree = values.ge(threshold).fillna(False).to_numpy()
        m = FS_M_PROBABILITIES[field]
        u = FS_U_PROBABILITIES[field]
        score += np.where(agree, np.log(m / u), np.log((1 - m) / (1 - u)))
    return pd.Series(score, index=frame.index)


def load_syn(world):
    data = load_benchmark_data(ROOT, VERSION, 'central_provisional', world, world)
    scoped = scoped_sources(data)
    ids = set(scoped['notice_id'].astype(str))
    tr = true_match_pairs(data)
    tin = tr.loc[tr['notice_a'].astype(str).isin(ids) & tr['notice_b'].astype(str).isin(ids)]
    truth_set = _pair_key_set(tin, 'notice_a', 'notice_b')
    pairs = _generate_candidates(scoped, cfg, window=None)
    scored = _pair_scores(pairs, truth_set)
    scored = add_source_candidate_context(scored, scoped)
    scored['fs_log_odds'] = fellegi_sunter_log_odds(scored)
    scored['scenario'] = 'central_provisional'
    scored['world'] = world
    return scored

fit = pd.concat([load_syn(w) for w in ['001', '002', '003', '004']], ignore_index=True)
cal = pd.concat([load_syn(w) for w in ['005', '006']], ignore_index=True)
real = pd.read_csv(OUT / 'real_candidate_pairs_reproduced.csv')
print(f'synthetic fit pairs {len(fit)}, calibration {len(cal)}, real pairs {len(real)}')
threshold_table = pd.read_csv(
    ROOT / 'reports/tables/synthetic_benchmark/v0_4_population_alias_revision'
    / 'linkage_algorithm_benchmark/algorithm_thresholds.csv'
).set_index('algorithm')

def prep(df):
    x = df.reindex(columns=FEATS).copy()
    for c in BIN:
        x[c] = pd.to_numeric(x[c], errors='coerce').astype(float)
    for c in CAT:
        x[c] = x[c].astype(str)
    return x


def select_top_links(frame: pd.DataFrame, score_col: str, threshold: float) -> pd.DataFrame:
    leading = [c for c in ['scenario', 'world'] if c in frame.columns]
    sort_cols = leading + ['source_notice_id', score_col, 'candidate_date']
    ascending = [True] * len(leading) + [True, False, True]
    group_cols = leading + ['source_notice_id']
    top = frame.sort_values(sort_cols, ascending=ascending)
    top = top.groupby(group_cols, as_index=False).head(1)
    return top.loc[top[score_col].ge(threshold)].copy()


try:
    one_hot_lr = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
    one_hot_gb = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
except TypeError:
    one_hot_lr = OneHotEncoder(handle_unknown='ignore', sparse=False)
    one_hot_gb = OneHotEncoder(handle_unknown='ignore', sparse=False)

pre_lr = ColumnTransformer([('num', Pipeline([('i', SimpleImputer(strategy='median')),
                                              ('s', StandardScaler())]), NUM + BIN),
                            ('cat', Pipeline([('i', SimpleImputer(strategy='most_frequent')),
                                              ('o', one_hot_lr)]), CAT)])
pre_gb = ColumnTransformer([('num', Pipeline([('i', SimpleImputer(strategy='median'))]), NUM + BIN),
                            ('cat', Pipeline([('i', SimpleImputer(strategy='most_frequent')),
                                              ('o', one_hot_gb)]), CAT)])
models = {
    'gradient_boosting': Pipeline([('p', pre_gb),
                                   ('m', GradientBoostingClassifier(
                                       n_estimators=160, learning_rate=0.045,
                                       max_depth=3, subsample=0.8,
                                       random_state=RANDOM_SEED))]),
    'logistic_regression': Pipeline([('p', pre_lr),
                                     ('m', LogisticRegression(
                                         max_iter=1000, class_weight='balanced',
                                         random_state=RANDOM_SEED))]),
}

real_sources = pd.read_csv(ROOT / 'data/processed/boamp_only/boamp_only_sources.csv',
                           low_memory=False)
for c in ['publication_date', 'start_date', 'estimated_end_date',
          'study_end_date']:
    if c in real_sources.columns:
        real_sources[c] = pd.to_datetime(real_sources[c], errors='coerce')

rows = []
rank1 = real.sort_values(['source_notice_id', 'composite_score'], ascending=[True, False]).copy()
rank1 = rank1[rank1['candidate_rank'].eq(1)].copy()
real_scored = rank1[['source_notice_id', 'candidate_notice_id', 'candidate_rank',
                     'n_candidates_for_source', 'top1_top2_margin',
                     'composite_score', 's_text', 's_cpv', 's_time',
                     's_buyer', 'gap_months', 'abs_gap_to_expected_end']].copy()
link_outputs = {}
survival_outputs = {}

for nm, mdl in models.items():
    mdl.fit(prep(fit), fit['is_true_match'].astype(int))
    score_col = 'gradient_boosting_score' if nm == 'gradient_boosting' else 'logistic_score'
    cal[score_col] = mdl.predict_proba(prep(cal))[:, 1]
    real[score_col] = mdl.predict_proba(prep(real))[:, 1]
    best_t = float(threshold_table.loc[nm, 'threshold'])
    cal_top = select_top_links(cal, score_col, best_t)
    if len(cal_top):
        best_f1 = float(
            precision_recall_fscore_support(
                cal_top['is_true_match'].astype(int),
                np.ones(len(cal_top), dtype=int),
                average='binary',
                zero_division=0,
            )[2]
        )
    else:
        best_f1 = 0.0

    real_p = mdl.predict_proba(prep(real))[:, 1]
    real[score_col] = real_p
    real_top = select_top_links(real, score_col, best_t)
    real_top['variant'] = f'{nm}_synthetic_v0_4_transfer'
    real_top['threshold_used'] = best_t
    tier_frame = real_top.copy()
    tier_frame['composite_score'] = tier_frame[score_col]
    real_top['confidence_tier'] = assign_confidence_tier(tier_frame, cfg)
    real_top['transfer_score'] = real_top[score_col]
    real_top['model_name'] = nm
    real_top['benchmark_version'] = VERSION
    real_top['threshold_source'] = 'central_calibration_worlds_005_006_rank1_f1_max'
    out_cols = [
        'source_notice_id', 'candidate_notice_id', 'source_date',
        'candidate_date', 'buyer_key', 'buyer_key_type', 'gap_months',
        'expected_end_date', 'abs_gap_to_expected_end', 's_time', 's_text',
        's_cpv', 's_buyer', 'composite_score', score_col, 'transfer_score',
        'candidate_rank', 'top1_top2_margin', 'n_candidates_for_source',
        'confidence_tier', 'variant', 'threshold_used', 'model_name',
        'benchmark_version', 'threshold_source',
    ]
    link_outputs[nm] = real_top[[c for c in out_cols if c in real_top.columns]].copy()
    sv = build_survival_dataset(
        real_sources, link_outputs[nm], f'{nm}_synthetic_v0_4_transfer', cfg,
        extra_link_cols=['transfer_score', score_col, 'threshold_used',
                         'model_name', 'benchmark_version', 'threshold_source',
                         'top1_top2_margin', 'n_candidates_for_source'])
    sv.to_csv(ROOT / f'data/processed/boamp_only/boamp_only_survival_{nm}_synthetic_v0_4_transfer.csv',
              index=False)
    survival_outputs[nm] = sv

    top_scores = real.sort_values(['source_notice_id', score_col], ascending=[True, False])
    top_scores = top_scores.groupby('source_notice_id', as_index=False).head(1)
    real_scored[score_col] = rank1['source_notice_id'].map(
        top_scores.set_index('source_notice_id')[score_col])
    rows.append(dict(
        model=nm, synthetic_threshold=float(best_t), synthetic_cal_f1=float(best_f1),
        syn_cal_score_p50=float(np.median(cal[score_col])),
        syn_cal_score_p90=float(np.quantile(cal[score_col], .9)),
        real_score_p50=float(np.median(real_p)), real_score_p90=float(np.quantile(real_p, .9)),
        real_pairs_above_threshold=int((real_p >= best_t).sum()),
        real_rank1_above_threshold=int(len(real_top)),
        implied_real_link_rate=float(len(real_top) / len(real_sources)),
        syn_cal_positive_rate=float((cal[score_col] >= best_t).mean()),
        real_positive_rate=float((real_p >= best_t).mean())))
    print(f'{nm}: rank-1 calibrated threshold={best_t:.4f} -> real accepts='
          f'{len(real_top)} (link rate {len(real_top)/len(real_sources):.4f})',
          flush=True)

tr = pd.DataFrame(rows)
tr.to_csv(OUT / 'synthetic_to_real_transfer_test.csv', index=False)
pd.concat(link_outputs.values(), ignore_index=True).to_csv(
    OUT / 'real_supervised_transfer_links.csv', index=False)
real_scored.to_csv(OUT / 'real_supervised_rank1_scored.csv', index=False)

sv_composite_balanced = pd.read_csv(
    ROOT / 'data/processed/boamp_only/boamp_only_survival_primary_balanced.csv')
sv_composite_strict = pd.read_csv(
    ROOT / 'data/processed/boamp_only/boamp_only_survival_conservative_strict.csv')
sv_composite_broad = pd.read_csv(
    ROOT / 'data/processed/boamp_only/boamp_only_survival_baseline_broad.csv')
gbm_primary_links = link_outputs['gradient_boosting'].copy()
gbm_primary_links['variant'] = 'primary_gbm'
gbm_primary_links.to_csv(OUT / 'real_primary_gbm_links.csv', index=False)
primary_gbm_survival = build_survival_dataset(
    real_sources,
    gbm_primary_links,
    'primary_gbm',
    cfg,
    extra_link_cols=[
        'transfer_score', 'gradient_boosting_score', 'threshold_used',
        'model_name', 'benchmark_version', 'threshold_source',
        'top1_top2_margin', 'n_candidates_for_source',
    ],
)
primary_gbm_survival.to_csv(
    ROOT / 'data/processed/boamp_only/boamp_only_survival_primary_gbm.csv',
    index=False,
)
composite_baseline_path = (
    ROOT / 'data/processed/boamp_only/boamp_only_survival_baseline_composite_balanced.csv'
)
composite_baseline_survival = sv_composite_balanced.copy()
composite_baseline_survival['variant'] = 'baseline_composite_balanced'
composite_baseline_survival.to_csv(composite_baseline_path, index=False)

def accepted_source_set(sv: pd.DataFrame) -> set[str]:
    return set(sv.loc[sv['event'].eq(1), 'notice_id'].astype(str))

sets = {
    'primary_gbm': set(gbm_primary_links['source_notice_id'].astype(str)),
    'baseline_composite_balanced': accepted_source_set(sv_composite_balanced),
    'conservative_composite_strict': accepted_source_set(sv_composite_strict),
    'sensitivity_logistic_regression': set(link_outputs['logistic_regression']['source_notice_id'].astype(str)),
    'sensitivity_composite_broad': accepted_source_set(sv_composite_broad),
}
agreement_rows = []
all_sources = set(real_sources['notice_id'].astype(str))
for name, source_set in sets.items():
    agreement_rows.append(dict(method=name, n_accepted=len(source_set),
                               link_rate=len(source_set) / len(all_sources)))
for a in sets:
    for b in sets:
        if a >= b:
            continue
        both = sets[a] & sets[b]
        agreement_rows.append(dict(
            method=f'{a}__AND__{b}', n_accepted=len(both),
            link_rate=len(both) / len(all_sources),
            only_a=len(sets[a] - sets[b]), only_b=len(sets[b] - sets[a])))
pd.DataFrame(agreement_rows).to_csv(OUT / 'real_supervised_method_agreement.csv',
                                    index=False)
pd.DataFrame(agreement_rows).to_csv(OUT / 'real_linkage_method_agreement.csv',
                                    index=False)

strategy_rows = [
    dict(
        role='primary_practical_linkage',
        method='gradient_boosting',
        decision_rule='rank1_score_above_frozen_synthetic_threshold',
        threshold=float(threshold_table.loc['gradient_boosting', 'threshold']),
        n_links=len(gbm_primary_links),
        link_rate=len(gbm_primary_links) / len(real_sources),
        links_path='reports/tables/real_linkage_freeze/real_primary_gbm_links.csv',
        survival_path='data/processed/boamp_only/boamp_only_survival_primary_gbm.csv',
        evidence_status='benchmark_supported_real_unlabelled',
        caveat='not real precision/recall; manual audit required',
    ),
    dict(
        role='transparent_baseline',
        method='composite_balanced',
        decision_rule='rank1_composite_above_frozen_balanced_threshold',
        threshold=float(P.thresholds.balanced),
        n_links=int(sv_composite_balanced['event'].sum()),
        link_rate=float(sv_composite_balanced['event'].mean()),
        links_path='reports/tables/real_linkage_freeze/real_candidate_pairs_reproduced.csv',
        survival_path='data/processed/boamp_only/boamp_only_survival_baseline_composite_balanced.csv',
        evidence_status='transparent_unfitted_baseline',
        caveat='weights are fixed, not real-label learned',
    ),
    dict(
        role='conservative_rule',
        method='composite_strict_no_potential',
        decision_rule='rank1_composite_above_strict_threshold_and_margin_not_potential',
        threshold=float(P.thresholds.strict),
        n_links=int(sv_composite_strict['event'].sum()),
        link_rate=float(sv_composite_strict['event'].mean()),
        links_path='reports/tables/real_linkage_freeze/decision_rule_summary.csv',
        survival_path='data/processed/boamp_only/boamp_only_survival_conservative_strict.csv',
        evidence_status='high_precision_sensitivity_not_label_validated',
        caveat='rule-based confidence tier, not empirical correctness probability',
    ),
    dict(
        role='recall_sensitivity',
        method='composite_broad',
        decision_rule='rank1_composite_above_frozen_broad_threshold',
        threshold=float(P.thresholds.broad),
        n_links=int(sv_composite_broad['event'].sum()),
        link_rate=float(sv_composite_broad['event'].mean()),
        links_path='reports/tables/real_linkage_freeze/decision_rule_summary.csv',
        survival_path='data/processed/boamp_only/boamp_only_survival_baseline_broad.csv',
        evidence_status='linkage_sensitivity',
        caveat='not selected by target link rate',
    ),
    dict(
        role='supervised_sensitivity',
        method='logistic_regression',
        decision_rule='rank1_score_above_frozen_synthetic_threshold',
        threshold=float(threshold_table.loc['logistic_regression', 'threshold']),
        n_links=len(link_outputs['logistic_regression']),
        link_rate=len(link_outputs['logistic_regression']) / len(real_sources),
        links_path='reports/tables/real_linkage_freeze/real_supervised_transfer_links.csv',
        survival_path='data/processed/boamp_only/boamp_only_survival_logistic_regression_synthetic_v0_4_transfer.csv',
        evidence_status='supervised_sensitivity',
        caveat='not real precision/recall; manual audit required',
    ),
]
pd.DataFrame(strategy_rows).to_csv(OUT / 'real_linkage_strategy_summary.csv',
                                   index=False)
json.dump(
    {
        'run_id': 'real_linkage_strategy_gbm_primary',
        'repository_commit': git_value('rev-parse', 'HEAD'),
        'repository_branch': git_value('branch', '--show-current'),
        'benchmark_version': VERSION,
        'candidate_generator': 'dur_w6_same_buyer_expected_end_window_top30',
        'primary_practical_model': 'gradient_boosting',
        'primary_threshold': float(threshold_table.loc['gradient_boosting', 'threshold']),
        'transparent_baseline': 'composite_balanced',
        'conservative_rule': 'composite_strict_no_potential',
        'real_precision_recall_status': 'UNKNOWN',
        'manual_audit_required': True,
        'strategy_summary_path': 'reports/tables/real_linkage_freeze/real_linkage_strategy_summary.csv',
        'strategy_survival_path': 'reports/tables/real_linkage_freeze/real_linkage_strategy_survival_headline.csv',
    },
    open(OUT / 'real_linkage_strategy_manifest.json', 'w'),
    indent=2,
)

strategy_survival_inputs = {
    'primary_practical_linkage__gbm': primary_gbm_survival,
    'transparent_baseline__composite_balanced': sv_composite_balanced,
    'conservative_rule__composite_strict': sv_composite_strict,
    'recall_sensitivity__composite_broad': sv_composite_broad,
    'supervised_sensitivity__logistic_regression': survival_outputs['logistic_regression'],
}
strategy_survival_rows = []
for role_method, sv in strategy_survival_inputs.items():
    kmf = KaplanMeierFitter().fit(
        sv['time_to_event_or_censor_months'],
        sv['event'],
        label=role_method,
    )
    med = kmf.median_survival_time_
    strategy_survival_rows.append(dict(
        role_method=role_method,
        n=len(sv),
        events=int(sv['event'].sum()),
        event_rate=float(sv['event'].mean()),
        censoring_rate=float(1 - sv['event'].mean()),
        median_survival=float(med) if np.isfinite(med) else np.nan,
        rmst60=float(restricted_mean_survival_time(
            kmf, t=P.survival.rmst_horizon_months)),
        surv_12m=float(kmf.predict(12)),
        surv_24m=float(kmf.predict(24)),
    ))
pd.DataFrame(strategy_survival_rows).to_csv(
    OUT / 'real_linkage_strategy_survival_headline.csv',
    index=False,
)

survival_rows = []
for nm, sv in survival_outputs.items():
    kmf = KaplanMeierFitter().fit(
        sv['time_to_event_or_censor_months'],
        sv['event'],
        label=nm,
    )
    med = kmf.median_survival_time_
    survival_rows.append(dict(
        model=nm,
        n=len(sv),
        events=int(sv['event'].sum()),
        event_rate=float(sv['event'].mean()),
        censoring_rate=float(1 - sv['event'].mean()),
        median_survival=float(med) if np.isfinite(med) else np.nan,
        rmst60=float(restricted_mean_survival_time(
            kmf, t=P.survival.rmst_horizon_months)),
        surv_12m=float(kmf.predict(12)),
        surv_24m=float(kmf.predict(24)),
    ))
pd.DataFrame(survival_rows).to_csv(
    OUT / 'real_supervised_survival_headline.csv', index=False)

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
