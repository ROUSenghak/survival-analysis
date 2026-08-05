"""Real BOAMP candidate-generator sensitivity + survival sensitivity.

Variant family is the one documented in config/pipeline.yaml:
  temporal_window.sensitivity_windows_months = [6, 9, 12, 18]   (6 = canonical)
  evaluation.duration_leakage_forward_months = 24               (duration-free route)
"""
from __future__ import annotations
import json, sys, time, warnings
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
from boamp.linkage.scoring import build_tfidf_matrix
from boamp.survival.datasets import build_survival_dataset
from boamp.validation.linkage_quality import forward_pairs, make_links_from_pairs
from lifelines import KaplanMeierFitter
from lifelines.utils import restricted_mean_survival_time

cfg = load_config(ROOT); P = cfg.pipeline
MAXC = P.candidates.max_candidates_per_source

clean = pd.read_csv(ROOT / 'data/interim/boamp_common_prepared.csv', low_memory=False)
for c in ['publication_date', 'start_date']:
    clean[c] = pd.to_datetime(clean[c], errors='coerce')
sources, info = build_source_population(clean, cfg)
eligible = sources[sources['buyer_key_type'] != 'MISSING']

def km_stats(sv):
    kmf = KaplanMeierFitter().fit(sv['time_to_event_or_censor_months'], sv['event'])
    med = kmf.median_survival_time_
    rmst = restricted_mean_survival_time(kmf, t=P.survival.rmst_horizon_months)
    return med, rmst

rows = []
for w in P.temporal_window.sensitivity_windows_months:
    t0 = time.time()
    pairs, _ = generate_pairs_single_key(sources, cfg, verbose=False, window_override=w)
    secs = time.time() - t0
    nc = pairs.groupby('source_notice_id').size()
    lk = build_links(pairs, P.thresholds.balanced, f'window_{w}m', cfg)
    sv = build_survival_dataset(sources, lk, f'window_{w}m', cfg)
    med, rmst = km_stats(sv)
    rows.append(dict(
        variant=f'dur_w{w}', rule='balanced_frozen_threshold', window_months=w,
        n_pairs=len(pairs), sources_with_candidate=int(pairs.source_notice_id.nunique()),
        sources_no_candidate=int(len(eligible) - pairs.source_notice_id.nunique()),
        cand_median=float(nc.median()), cand_q90=float(nc.quantile(.9)),
        cand_q99=float(nc.quantile(.99)), cap_rate=float((nc >= MAXC).mean()),
        seconds=round(secs, 1), n_links=len(lk), link_rate=len(lk) / len(sources),
        n_potential=int((lk.confidence_tier == 'POTENTIAL').sum()),
        censoring_rate=float(1 - sv.event.mean()),
        median_survival=float(med) if np.isfinite(med) else np.nan,
        rmst60=float(rmst),
        median_gap_linked=float(lk.gap_months.median()) if len(lk) else np.nan))
    print(f'dur_w{w}: pairs={len(pairs)} links={len(lk)} rmst60={rmst:.2f}', flush=True)

# duration-free forward route (documented leakage check)
t0 = time.time()
el = eligible.sort_values(['buyer_key', 'publication_date']).reset_index(drop=True)
_v, tfidf = build_tfidf_matrix(el['objet_clean'].fillna('').tolist(), cfg)
fp = forward_pairs(el, tfidf, cfg, months=P.evaluation.duration_leakage_forward_months)
secs = time.time() - t0
nc = fp.groupby('source_notice_id').size()
f_links, f_thr = make_links_from_pairs(fp, 'forward_24m_no_duration',
                                       'score_forward_no_duration')
sv = build_survival_dataset(sources, f_links, 'forward_24m_no_duration', cfg)
med, rmst = km_stats(sv)
rows.append(dict(
    variant='fwd24_no_duration', rule='rank1_median_rederived', window_months=24,
    n_pairs=len(fp), sources_with_candidate=int(fp.source_notice_id.nunique()),
    sources_no_candidate=int(len(eligible) - fp.source_notice_id.nunique()),
    cand_median=float(nc.median()), cand_q90=float(nc.quantile(.9)),
    cand_q99=float(nc.quantile(.99)), cap_rate=float((nc >= MAXC).mean()),
    seconds=round(secs, 1), n_links=len(f_links), link_rate=len(f_links) / len(sources),
    n_potential=np.nan, censoring_rate=float(1 - sv.event.mean()),
    median_survival=float(med) if np.isfinite(med) else np.nan, rmst60=float(rmst),
    median_gap_linked=float(f_links.gap_months.median()) if len(f_links) else np.nan))
print(f'fwd24: pairs={len(fp)} links={len(f_links)} thr={f_thr:.4f} rmst60={rmst:.2f}')

df = pd.DataFrame(rows)
df.to_csv(OUT / 'real_candidate_generator_sensitivity.csv', index=False)
print('\n' + df.to_string(index=False))
