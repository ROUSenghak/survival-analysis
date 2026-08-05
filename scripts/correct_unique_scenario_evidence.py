"""Recompute benchmark artifact counts and cross-scenario evidence using UNIQUE
scenarios only.

`moderate` is a byte-identical duplicate of `central_provisional`: its config sets
extends: central_provisional with a difficulty ratio of 1.000, every world seed is
shared, and observed_notices.parquet hashes are equal. Counting it as independent
evidence inflates artifact counts and every cross-scenario stability statistic.
"""
from __future__ import annotations
import hashlib, json, glob, os
from pathlib import Path
import pandas as pd

ROOT = Path('/home/senghakrou/survival-analysis')
BASE = ROOT / 'data/processed/synthetic_benchmark/v0_4_population_alias_revision'
OUT = ROOT / 'reports/tables/real_linkage_freeze'
OUT.mkdir(parents=True, exist_ok=True)

# ---- prove the duplication, per world, by content hash of the observed notices
rows = []
for world in sorted(os.listdir(BASE / 'central_provisional')):
    h = {}
    for scen in ['central_provisional', 'moderate']:
        p = glob.glob(str(BASE / scen / world / 'corruption_*/observed_notices.parquet'))
        if not p:
            h[scen] = None; continue
        h[scen] = hashlib.sha256(open(p[0], 'rb').read()).hexdigest()
    rows.append(dict(world=world, central_sha256=h['central_provisional'],
                     moderate_sha256=h['moderate'],
                     identical=h['central_provisional'] == h['moderate']))
dup = pd.DataFrame(rows)
dup.to_csv(OUT / 'moderate_duplicate_evidence.csv', index=False)
print(f'worlds compared: {len(dup)}  identical observed_notices: {int(dup.identical.sum())}')

# ---- corrected artifact inventory
rep = json.load(open(ROOT / 'reports/tables/synthetic_benchmark/'
                     'v0_4_population_alias_revision/validation_framework/replay_replicates.json'))
inv = pd.DataFrame([{'scenario': r.get('scenario'), 'status': r.get('status')}
                    for r in rep['replicates']])
counts = inv.groupby('scenario').size().rename('replicates').reset_index()
counts['unique_evidence'] = counts.scenario != 'moderate'
counts.to_csv(OUT / 'corrected_artifact_inventory.csv', index=False)
total = int(counts.replicates.sum())
unique = int(counts.loc[counts.unique_evidence, 'replicates'].sum())
print(f'\nreplayed artifacts as reported : {total}')
print(f'unique (moderate excluded)     : {unique}')
print(f'scenarios as reported          : {counts.scenario.nunique()}')
print(f'unique scenarios               : {int(counts.unique_evidence.sum())}')
print(counts.to_string(index=False))

# ---- corrected pooled blocking recall
meta = pd.read_csv(ROOT / 'reports/tables/synthetic_benchmark/'
                   'v0_4_population_alias_revision/linkage_algorithm_benchmark/'
                   'world_candidate_metadata.csv')
ev = meta[meta.split == 'evaluation']
allw = ev.n_reachable_truth.sum() / ev.n_truth_in_scope.sum()
uni = ev[ev.scenario != 'moderate']
uniw = uni.n_reachable_truth.sum() / uni.n_truth_in_scope.sum()
summary = dict(
    pooled_blocking_recall_as_reported=float(allw),
    pooled_blocking_recall_unique_scenarios=float(uniw),
    n_eval_worlds_as_reported=int(len(ev)),
    n_eval_worlds_unique=int(len(uni)),
    replayed_artifacts_as_reported=total,
    replayed_artifacts_unique=unique,
    scenarios_as_reported=int(counts.scenario.nunique()),
    scenarios_unique=int(counts.unique_evidence.sum()))
json.dump(summary, open(OUT / 'corrected_cross_scenario_evidence.json', 'w'), indent=2)
print('\n' + json.dumps(summary, indent=2))
