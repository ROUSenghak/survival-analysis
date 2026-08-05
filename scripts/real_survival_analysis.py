"""Real BOAMP survival analysis under the three frozen linkage rules,
plus linkage-sensitivity across the documented candidate-window family."""
from __future__ import annotations
import json, sys, warnings
from pathlib import Path
import numpy as np, pandas as pd

warnings.filterwarnings('ignore')
ROOT = Path('/home/senghakrou/survival-analysis')
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'reports/tables/real_linkage_freeze'
FIG = ROOT / 'reports/figures/real_linkage_freeze'
FIG.mkdir(parents=True, exist_ok=True)

from boamp.config import load_config
from lifelines import KaplanMeierFitter, CoxPHFitter
from lifelines.statistics import logrank_test
from lifelines.utils import restricted_mean_survival_time
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

cfg = load_config(ROOT); P = cfg.pipeline
RULES = ['primary_balanced', 'conservative_strict', 'baseline_broad']
H = P.survival.rmst_horizon_months

svs = {r: pd.read_csv(ROOT / f'data/processed/boamp_only/boamp_only_survival_{r}.csv')
       for r in RULES}

# ------------------------------------------------- headline survival by rule
rows = []
for r, sv in svs.items():
    T, E = sv['time_to_event_or_censor_months'], sv['event']
    kmf = KaplanMeierFitter().fit(T, E)
    med = kmf.median_survival_time_
    rmst = restricted_mean_survival_time(kmf, t=H)
    ev = sv[sv.event == 1]['time_to_event_or_censor_months']
    rows.append(dict(rule=r, n=len(sv), events=int(E.sum()),
                     event_rate=float(E.mean()), censoring_rate=float(1 - E.mean()),
                     median_survival=float(med) if np.isfinite(med) else np.nan,
                     rmst60=float(rmst),
                     surv_12m=float(kmf.predict(12)), surv_24m=float(kmf.predict(24)),
                     surv_36m=float(kmf.predict(36)),
                     event_gap_p25=float(ev.quantile(.25)), event_gap_p50=float(ev.median()),
                     event_gap_p75=float(ev.quantile(.75))))
hl = pd.DataFrame(rows)
hl.to_csv(OUT / 'survival_headline_by_rule.csv', index=False)
print(hl.to_string(index=False))

# ------------------------------------------------- KM figure
fig, ax = plt.subplots(figsize=(7.5, 5))
for r, sv in svs.items():
    KaplanMeierFitter().fit(sv['time_to_event_or_censor_months'], sv['event'],
                            label=r).plot_survival_function(ax=ax, ci_show=True)
ax.set_xlabel('months since publication'); ax.set_ylabel('S(t) — not yet renewed')
ax.set_title('Time to observed renewal, Layer 1, by linkage decision rule')
ax.set_xlim(0, 60); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(FIG / 'km_by_linkage_rule.png', dpi=150)
fig.savefig(FIG / 'km_by_linkage_rule.pdf'); plt.close(fig)

# ------------------------------------------------- subgroup KM + logrank (primary)
sub_rows = []
for r, sv in svs.items():
    sv = sv.copy()
    sv['cpv_division'] = sv['cpv_division'].astype(str).str.replace(r'\.0$', '', regex=True)
    sv['dur_imputed'] = sv['dur_was_imputed'].astype(str)
    for dim in ['buyer_key_type', 'category_label', 'dur_imputed']:
        vc = sv[dim].value_counts()
        keep = vc[vc >= P.survival.km_strata_min_group_size].index
        levels = list(keep)
        for lv in levels:
            g = sv[sv[dim] == lv]
            kmf = KaplanMeierFitter().fit(g['time_to_event_or_censor_months'], g['event'])
            sub_rows.append(dict(rule=r, dimension=dim, level=str(lv), n=len(g),
                                 events=int(g.event.sum()), event_rate=float(g.event.mean()),
                                 rmst60=float(restricted_mean_survival_time(kmf, t=H))))
        if len(levels) == 2:
            a, b = sv[sv[dim] == levels[0]], sv[sv[dim] == levels[1]]
            lr = logrank_test(a['time_to_event_or_censor_months'], b['time_to_event_or_censor_months'],
                              a['event'], b['event'])
            sub_rows.append(dict(rule=r, dimension=dim + '__logrank', level=f'{levels[0]} vs {levels[1]}',
                                 n=len(sv), events=int(sv.event.sum()), event_rate=np.nan,
                                 rmst60=float(lr.p_value)))
pd.DataFrame(sub_rows).to_csv(OUT / 'survival_subgroups_by_rule.csv', index=False)
print(f'\nsubgroup rows: {len(sub_rows)}')

# ------------------------------------------------- Cox under each rule
cox_rows = []
for r, sv in svs.items():
    d = sv.copy()
    d['cpv_division'] = d['cpv_division'].astype(str).str.replace(r'\.0$', '', regex=True)
    top = d['cpv_division'].value_counts().head(5).index
    d['cpv_div_grp'] = np.where(d['cpv_division'].isin(top), d['cpv_division'], 'OTHER')
    d['pub_year'] = pd.to_datetime(d['publication_date']).dt.year
    X = pd.get_dummies(
        d[['time_to_event_or_censor_months', 'event', 'declared_duration_months',
           'dur_was_imputed', 'buyer_key_type', 'cpv_div_grp', 'pub_year']],
        columns=['buyer_key_type', 'cpv_div_grp'], drop_first=True)
    X['dur_was_imputed'] = X['dur_was_imputed'].astype(int)
    X = X.dropna()
    try:
        cph = CoxPHFitter(penalizer=P.survival.cox_penalizer).fit(
            X, 'time_to_event_or_censor_months', 'event')
        s = cph.summary
        for cov in s.index:
            cox_rows.append(dict(rule=r, covariate=cov, coef=float(s.loc[cov, 'coef']),
                                 hazard_ratio=float(s.loc[cov, 'exp(coef)']),
                                 ci_low=float(s.loc[cov, 'exp(coef) lower 95%']),
                                 ci_high=float(s.loc[cov, 'exp(coef) upper 95%']),
                                 p=float(s.loc[cov, 'p'])))
        print(f'{r}: Cox fitted, concordance={cph.concordance_index_:.4f}, n={len(X)}')
        cox_rows.append(dict(rule=r, covariate='__concordance__',
                             coef=np.nan, hazard_ratio=float(cph.concordance_index_),
                             ci_low=np.nan, ci_high=np.nan, p=np.nan))
    except Exception as e:
        print(f'{r}: Cox failed: {e}')
pd.DataFrame(cox_rows).to_csv(OUT / 'survival_cox_by_rule.csv', index=False)

# ------------------------------------------------- conclusion stability
piv = pd.DataFrame(cox_rows)
piv = piv[piv.covariate != '__concordance__']
stab = piv.pivot_table(index='covariate', columns='rule', values='hazard_ratio')
sign = piv.assign(dir=np.sign(piv.coef)).pivot_table(index='covariate', columns='rule', values='dir')
stab['sign_consistent'] = sign.nunique(axis=1).eq(1)
stab.to_csv(OUT / 'cox_hazard_ratio_stability.csv')
print('\nCox HR across rules (sign consistency):')
print(stab.to_string())
print('\nDONE ->', OUT)
