"""Stratified real-BOAMP audit samples for manual review.

The current real-linkage strategy uses GBM as the primary practical method,
with the composite balanced rule retained as the transparent baseline. The
sample therefore emphasizes GBM/composite agreement and disagreement, while
still retaining rejected and no-candidate cases. It is reproducible under the
recorded seed and carries blank reviewer columns.
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
from boamp.status import MANUAL_AUDIT_LABELS

cfg = load_config(ROOT); P = cfg.pipeline
SEED = P.run.random_seed
rng = np.random.default_rng(SEED)

clean = pd.read_csv(ROOT / 'data/interim/boamp_common_prepared.csv', low_memory=False)
for c in ['publication_date', 'start_date']:
    clean[c] = pd.to_datetime(clean[c], errors='coerce')
sources, _ = build_source_population(clean, cfg)
pairs = pd.read_csv(OUT / 'real_candidate_pairs_reproduced.csv')
composite_links = build_links(pairs, P.thresholds.balanced, 'baseline_composite_balanced', cfg)
gbm_links = pd.read_csv(OUT / 'real_primary_gbm_links.csv')

txt = clean.set_index('notice_id')['objet_clean'].to_dict()
name = clean.set_index('notice_id')['buyer_name_raw'].to_dict()
src_attr = sources.set_index('notice_id')
act = sources.groupby('buyer_key')['notice_id'].count()

r1 = pairs[pairs['candidate_rank'] == 1].copy()
gbm_ids = set(gbm_links['source_notice_id'].astype(str))
composite_ids = set(composite_links['source_notice_id'].astype(str))
with_cand = set(pairs['source_notice_id'])
eligible = sources[sources['buyer_key_type'] != 'MISSING']

strata = {
    'gbm_and_composite': gbm_links[gbm_links['source_notice_id'].astype(str).isin(composite_ids)],
    'gbm_only': gbm_links[~gbm_links['source_notice_id'].astype(str).isin(composite_ids)],
    'composite_only': composite_links[~composite_links['source_notice_id'].astype(str).isin(gbm_ids)],
    'gbm_borderline_score': gbm_links[
        gbm_links['transfer_score'].between(
            gbm_links['threshold_used'],
            gbm_links['threshold_used'] + 0.05,
            inclusive='left',
        )
    ],
    'gbm_small_margin': gbm_links[
        gbm_links['top1_top2_margin'] < P.confidence_tiers.potential_margin_max
    ],
    'rejected_composite_top_candidate': r1[
        (~r1.source_notice_id.astype(str).isin(gbm_ids | composite_ids))
        & (r1.composite_score >= P.thresholds.broad)
    ],
    'rejected_far_below': r1[
        (~r1.source_notice_id.astype(str).isin(gbm_ids | composite_ids))
        & (r1.composite_score < P.thresholds.broad)
    ],
}

no_cand = eligible[~eligible['notice_id'].isin(with_cand)].copy()
no_cand['composite_score'] = np.nan
no_cand['candidate_notice_id'] = None
no_cand['top1_top2_margin'] = np.nan
no_cand['n_candidates_for_source'] = 0
no_cand['source_notice_id'] = no_cand['notice_id']
strata['censored_no_candidate'] = no_cand

QUOTA = {
    'gbm_and_composite': 18,
    'gbm_only': 14,
    'composite_only': 18,
    'gbm_borderline_score': 12,
    'gbm_small_margin': 12,
    'rejected_composite_top_candidate': 12,
    'rejected_far_below': 6,
    'censored_no_candidate': 8,
}

rows = []
used_sources = set()
for stratum, frame in strata.items():
    frame = frame[~frame['source_notice_id'].astype(str).isin(used_sources)].copy()
    n = min(QUOTA[stratum], len(frame))
    if n == 0:
        continue
    take = frame.sample(n=n, random_state=SEED)
    for _, r in take.iterrows():
        sid = r['source_notice_id']
        used_sources.add(str(sid))
        s = src_attr.loc[sid] if sid in src_attr.index else None
        cid = r.get('candidate_notice_id')
        sid_s = str(sid)
        gbm_row = gbm_links.loc[gbm_links['source_notice_id'].astype(str).eq(sid_s)]
        comp_row = composite_links.loc[composite_links['source_notice_id'].astype(str).eq(sid_s)]
        rows.append(dict(
            audit_stratum=stratum,
            source_notice_id=sid,
            candidate_notice_id=cid,
            gbm_candidate_notice_id=(gbm_row.iloc[0]['candidate_notice_id'] if len(gbm_row) else None),
            composite_candidate_notice_id=(comp_row.iloc[0]['candidate_notice_id'] if len(comp_row) else None),
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
            gbm_score=r.get('transfer_score'),
            top1_top2_margin=r.get('top1_top2_margin'),
            n_candidates_for_source=r.get('n_candidates_for_source'),
            gbm_decision=('LINKED' if sid_s in gbm_ids else
                          ('NO_CANDIDATE' if stratum == 'censored_no_candidate'
                           else 'NOT_LINKED')),
            composite_decision=('LINKED' if sid_s in composite_ids else
                                ('NO_CANDIDATE' if stratum == 'censored_no_candidate'
                                 else 'NOT_LINKED')),
            reason_code=stratum.upper(),
            rule_version='primary_gbm@0.230964__baseline_composite@0.343167',
            benchmark_version='real_boamp_layer1',
            reviewer_label='', reviewer_confidence='', reviewer_notes='',
            review_date='', needs_second_review=''))

audit = pd.DataFrame(rows)
audit.to_csv(OUT / 'real_audit_sample_100.csv', index=False)
audit30 = []
quota30 = {
    'gbm_and_composite': 4,
    'gbm_only': 4,
    'composite_only': 4,
    'gbm_borderline_score': 4,
    'gbm_small_margin': 4,
    'rejected_composite_top_candidate': 4,
    'rejected_far_below': 3,
    'censored_no_candidate': 3,
}
used30 = set()
for stratum, quota in quota30.items():
    frame = audit.loc[audit['audit_stratum'].eq(stratum)].copy()
    frame = frame[~frame['source_notice_id'].astype(str).isin(used30)]
    if frame.empty:
        continue
    take = frame.sample(n=min(quota, len(frame)), random_state=SEED)
    used30.update(take['source_notice_id'].astype(str))
    audit30.append(take)

audit30_df = pd.concat(audit30, ignore_index=True) if audit30 else audit.head(0).copy()
audit30_df = audit30_df.sort_values(
    ['audit_stratum', 'source_date', 'buyer_key_type', 'source_cpv'],
    na_position='last',
).reset_index(drop=True)
audit30_df.to_csv(cfg.paths.manual_audit_sample_30, index=False)

template_cols = list(audit30_df.columns)
template = pd.DataFrame(columns=template_cols)
template.to_csv(cfg.paths.manual_audit_entry_template, index=False)

label_list = "\n".join(f"- `{label}`" for label in sorted(MANUAL_AUDIT_LABELS))
instructions = f"""# Manual Audit Instructions

This package is for human review of real BOAMP linkage transfer. It does not
contain labels and must not be used to claim real precision or recall until a
human reviewer fills `reviewer_label`.

Canonical review file:
`{cfg.paths.manual_audit_sample_30.relative_to(ROOT)}`

Blank entry template:
`{cfg.paths.manual_audit_entry_template.relative_to(ROOT)}`

## Allowed Labels

{label_list}

## Review Procedure

1. Read the source notice evidence first: buyer, dates, CPV, duration flag, and
   source text.
2. If a candidate is present, compare the candidate notice against the source on
   buyer evidence, CPV evidence, chronology, text reuse, and substantive scope.
3. Use scores and method decisions only as context. Do not infer correctness
   from GBM, composite, thresholds, confidence tier, or acceptance status.
4. For no-candidate and rejected cases, decide whether the absence/rejection is
   credible from the evidence available in the row. Use `MISSED_LINK` only when
   the row evidence identifies a plausible successor that the method missed.
5. Leave uncertain cases as `INSUFFICIENT_INFORMATION` or
   `NEEDS_SECOND_REVIEW`; do not force a binary answer.

## Scientific Gate

Before the audit is complete, real precision and recall remain `UNKNOWN`. Event
and censoring datasets are provisional because an unlinked notice is operationally
censored, not a confirmed non-renewal.
"""
cfg.paths.manual_audit_instructions.write_text(instructions, encoding='utf-8')
print(f'audit sample rows: {len(audit)} (seed={SEED})')
print(f'canonical audit sample rows: {len(audit30_df)}')
print(audit.groupby('audit_stratum').size().to_string())
print('\nstratum populations available:')
for k, v in strata.items():
    print(f'  {k:<28} {len(v)}')
