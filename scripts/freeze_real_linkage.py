"""Reproduce real BOAMP Layer-1 linkage, run linkage diagnostics, and build the
event/censoring datasets under three frozen decision rules.

Everything uses the canonical package code and config/pipeline.yaml. No parameter
is re-derived here; thresholds are asserted against the frozen values.
"""
from __future__ import annotations
import json, sys, warnings
from pathlib import Path
import numpy as np, pandas as pd

warnings.filterwarnings('ignore')
ROOT = Path('/home/senghakrou/survival-analysis')
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'reports/tables/real_linkage_freeze'
OUT.mkdir(parents=True, exist_ok=True)

from boamp.config import load_config
from boamp.data.prepare import build_source_population
from boamp.linkage.candidates import generate_pairs_single_key
from boamp.linkage.links import build_links
from boamp.linkage.scoring import derive_thresholds, assert_thresholds_frozen
from boamp.survival.datasets import build_survival_dataset

cfg = load_config(ROOT)
P = cfg.pipeline

clean = pd.read_csv(ROOT / 'data/interim/boamp_common_prepared.csv', low_memory=False)
for c in ['publication_date', 'start_date', 'end_diffusion_date', 'response_deadline',
          'linked_attribution_date']:
    if c in clean.columns:
        clean[c] = pd.to_datetime(clean[c], errors='coerce')
print(f'prepared corpus rows: {len(clean)}')

sources, info = build_source_population(clean, cfg)
print(f'eligible source contracts: {len(sources)}  study_end={info["study_end_date"].date()}')

pairs, window = generate_pairs_single_key(sources, cfg, verbose=True)
print(f'candidate pairs: {len(pairs)}  window={window}m')

derived = derive_thresholds(pairs, cfg)
assert_thresholds_frozen(derived, cfg)
print('frozen thresholds asserted OK:', {k: round(v, 6) for k, v in derived.items()})

# ---------------------------------------------------------------- decision rules
THR = P.thresholds
RULES = {
    'primary_balanced':      dict(threshold=THR.balanced, high_conf_only=False),
    'conservative_strict':   dict(threshold=THR.strict,   high_conf_only=True),
    'baseline_broad':        dict(threshold=THR.broad,    high_conf_only=False),
}

link_sets, rule_rows = {}, []
for name, spec in RULES.items():
    lk = build_links(pairs, spec['threshold'], name, cfg)
    if spec['high_conf_only']:
        lk = lk[lk['confidence_tier'] != 'POTENTIAL'].copy()
    link_sets[name] = lk
    rule_rows.append(dict(
        rule=name, threshold=spec['threshold'], high_conf_only=spec['high_conf_only'],
        n_links=len(lk), link_rate=len(lk) / len(sources),
        n_potential=int((lk['confidence_tier'] == 'POTENTIAL').sum()),
        n_high=int((lk['confidence_tier'] == 'HIGH').sum()),
        n_medium=int((lk['confidence_tier'] == 'MEDIUM').sum())))
    print(f'{name:<22} links={len(lk):>5} rate={len(lk)/len(sources):.4f}')
pd.DataFrame(rule_rows).to_csv(OUT / 'decision_rule_summary.csv', index=False)

# ---------------------------------------------------------------- integrity checks
checks = {}
prim = link_sets['primary_balanced']
checks['n_sources'] = len(sources)
checks['n_candidate_pairs'] = len(pairs)
checks['window_months'] = int(window)
checks['self_links'] = int((prim['source_notice_id'] == prim['candidate_notice_id']).sum())
checks['non_forward_links'] = int((pd.to_datetime(prim['candidate_date'])
                                   <= pd.to_datetime(prim['source_date'])).sum())
checks['negative_gap'] = int((prim['gap_months'] <= 0).sum())
succ = prim['candidate_notice_id'].value_counts()
checks['successors_reused'] = int((succ > 1).sum())
checks['max_reuse_of_one_successor'] = int(succ.max()) if len(succ) else 0
checks['sources_with_multiple_links'] = int(
    (prim['source_notice_id'].value_counts() > 1).sum())
eligible = sources[sources['buyer_key_type'] != 'MISSING']
checks['n_eligible_for_linkage'] = len(eligible)
srcs_with_cand = pairs['source_notice_id'].nunique()
checks['sources_with_at_least_one_candidate'] = int(srcs_with_cand)
checks['sources_with_no_candidate'] = int(len(eligible) - srcs_with_cand)
# a source is "rejected" if it had a rank-1 candidate that fell below threshold
r1 = pairs[pairs['candidate_rank'] == 1]
checks['sources_rejected_top_candidate'] = int(
    (r1['composite_score'] < THR.balanced).sum())
checks['sources_accepted'] = int((r1['composite_score'] >= THR.balanced).sum())
checks['accepted_but_ambiguous_potential'] = int(
    (prim['confidence_tier'] == 'POTENTIAL').sum())
print('\nintegrity checks:', json.dumps(checks, indent=2, default=str))
json.dump(checks, open(OUT / 'linkage_integrity_checks.json', 'w'), indent=2, default=str)

# ---------------------------------------------------------------- linked vs unlinked bias
linked_ids = set(prim['source_notice_id'])
b = eligible.copy()
b['linked'] = b['notice_id'].isin(linked_ids)
b['publication_year'] = pd.to_datetime(b['publication_date']).dt.year
b['text_len'] = b['objet_clean'].fillna('').str.len()
b['cpv_missing'] = b['cpv_clean'].isna()
act = b.groupby('buyer_key')['notice_id'].transform('count')
b['buyer_activity_bin'] = pd.cut(act, [0, 1, 3, 10, 1e9],
                                 labels=['1', '2-3', '4-10', '11+'])
rows = []
def add(dim, series):
    t = pd.crosstab(series, b['linked'], normalize='index')
    n = pd.crosstab(series, b['linked']).sum(axis=1)
    for k in t.index:
        rows.append(dict(dimension=dim, level=str(k), n=int(n[k]),
                         link_rate=float(t.loc[k, True]) if True in t.columns else 0.0))
add('publication_year', b['publication_year'])
add('buyer_key_type', b['buyer_key_type'])
add('cpv_division', b['cpv_division'].astype(str))
add('category_label', b['category_label'].astype(str))
add('buyer_activity', b['buyer_activity_bin'].astype(str))
add('cpv_missing', b['cpv_missing'])
add('duration_imputed', b['dur_was_imputed'])
add('text_length_quartile', pd.qcut(b['text_len'], 4, labels=['Q1', 'Q2', 'Q3', 'Q4'],
                                    duplicates='drop').astype(str))
bias = pd.DataFrame(rows)
bias.to_csv(OUT / 'linked_vs_unlinked_bias.csv', index=False)
print(f'\nbias table rows: {len(bias)}  overall link rate: {b.linked.mean():.4f}')

# ---------------------------------------------------------------- survival datasets
sv_paths = {}
for name, lk in link_sets.items():
    sv = build_survival_dataset(sources, lk, name, cfg)
    p = ROOT / f'data/processed/boamp_only/boamp_only_survival_{name}.csv'
    sv.to_csv(p, index=False)
    sv_paths[name] = str(p.relative_to(ROOT))
    print(f'{name:<22} survival rows={len(sv)} events={int(sv.event.sum())} '
          f'censoring={1 - sv.event.mean():.4f}')

pairs.to_csv(OUT / 'real_candidate_pairs_reproduced.csv', index=False)
json.dump({'window_months': int(window), 'n_sources': len(sources),
           'n_pairs': len(pairs), 'thresholds': {k: float(v) for k, v in derived.items()},
           'survival_paths': sv_paths,
           'study_end_date': str(info['study_end_date'])},
          open(OUT / 'freeze_manifest.json', 'w'), indent=2)
print('\nDONE ->', OUT)
