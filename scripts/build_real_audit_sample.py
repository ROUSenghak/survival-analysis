"""Stratified real-BOAMP audit sample (~100 cases) for manual review.

The sample is drawn with the recorded seed (config run.random_seed) so it is
reproducible. It carries scores, margins, confidence tier, reason code and rule
version so a reviewer can adjudicate without re-running the pipeline.
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
from boamp.data.prepare import build_source_population
from boamp.linkage.links import build_links

cfg = load_config(ROOT); P = cfg.pipeline
SEED = P.run.random_seed
rng = np.random.default_rng(SEED)

clean = pd.read_csv(ROOT / 'data/interim/boamp_common_prepared.csv', low_memory=False)
for c in ['publication_date', 'start_date']:
    clean[c] = pd.to_datetime(clean[c], errors='coerce')
sources, _ = build_source_population(clean, cfg)
pairs = pd.read_csv(OUT / 'real_candidate_pairs_reproduced.csv')
links = build_links(pairs, P.thresholds.balanced, 'primary_balanced', cfg)

txt = clean.set_index('notice_id')['objet_clean'].to_dict()
name = clean.set_index('notice_id')['buyer_name_raw'].to_dict()
src_attr = sources.set_index('notice_id')
act = sources.groupby('buyer_key')['notice_id'].count()

r1 = pairs[pairs['candidate_rank'] == 1].copy()
linked_ids = set(links['source_notice_id'])
with_cand = set(pairs['source_notice_id'])
eligible = sources[sources['buyer_key_type'] != 'MISSING']

strata = {}
acc = r1[r1['source_notice_id'].isin(linked_ids)]
strata['accepted_high_confidence'] = acc[(acc.composite_score >= P.confidence_tiers.high_score_min)
                                         & (acc.top1_top2_margin >= P.confidence_tiers.potential_margin_max)]
strata['accepted_borderline_score'] = acc[(acc.composite_score >= P.thresholds.balanced)
                                          & (acc.composite_score < P.thresholds.balanced + 0.05)]
strata['accepted_ambiguous_margin'] = acc[acc.top1_top2_margin < P.confidence_tiers.potential_margin_max]
strata['rejected_top_candidate'] = r1[(~r1.source_notice_id.isin(linked_ids))
                                      & (r1.composite_score >= P.thresholds.broad)]
strata['rejected_far_below'] = r1[(~r1.source_notice_id.isin(linked_ids))
                                  & (r1.composite_score < P.thresholds.broad)]

no_cand = eligible[~eligible['notice_id'].isin(with_cand)].copy()
no_cand['composite_score'] = np.nan
no_cand['candidate_notice_id'] = None
no_cand['top1_top2_margin'] = np.nan
no_cand['n_candidates_for_source'] = 0
no_cand['source_notice_id'] = no_cand['notice_id']
strata['censored_no_candidate'] = no_cand

QUOTA = {'accepted_high_confidence': 18, 'accepted_borderline_score': 16,
         'accepted_ambiguous_margin': 16, 'rejected_top_candidate': 18,
         'rejected_far_below': 12, 'censored_no_candidate': 20}

rows = []
for stratum, frame in strata.items():
    n = min(QUOTA[stratum], len(frame))
    if n == 0:
        continue
    take = frame.sample(n=n, random_state=SEED)
    for _, r in take.iterrows():
        sid = r['source_notice_id']
        s = src_attr.loc[sid] if sid in src_attr.index else None
        cid = r.get('candidate_notice_id')
        rows.append(dict(
            audit_stratum=stratum,
            source_notice_id=sid,
            candidate_notice_id=cid,
            buyer_name=name.get(sid),
            buyer_key_type=s['buyer_key_type'] if s is not None else None,
            buyer_n_sources=int(act.get(s['buyer_key'], 0)) if s is not None else None,
            source_date=str(s['publication_date'])[:10] if s is not None else None,
            candidate_date=str(r.get('candidate_date'))[:10],
            gap_months=r.get('gap_months'),
            source_text=str(txt.get(sid))[:220],
            candidate_text=str(txt.get(cid))[:220] if cid is not None else None,
            source_cpv=s['cpv_clean'] if s is not None else None,
            category_label=s['category_label'] if s is not None else None,
            duration_imputed=s['dur_was_imputed'] if s is not None else None,
            s_text=r.get('s_text'), s_cpv=r.get('s_cpv'),
            s_time=r.get('s_time'), s_buyer=r.get('s_buyer'),
            composite_score=r.get('composite_score'),
            top1_top2_margin=r.get('top1_top2_margin'),
            n_candidates_for_source=r.get('n_candidates_for_source'),
            pipeline_decision=('LINKED' if sid in linked_ids else
                               ('NO_CANDIDATE' if stratum == 'censored_no_candidate'
                                else 'NOT_LINKED')),
            reason_code=stratum.upper(),
            rule_version='primary_balanced@0.343167',
            benchmark_version='real_boamp_layer1',
            reviewer_label='', reviewer_confidence='', reviewer_notes=''))

audit = pd.DataFrame(rows)
audit.to_csv(OUT / 'real_audit_sample_100.csv', index=False)
print(f'audit sample rows: {len(audit)} (seed={SEED})')
print(audit.groupby('audit_stratum').size().to_string())
print('\nstratum populations available:')
for k, v in strata.items():
    print(f'  {k:<28} {len(v)}')
