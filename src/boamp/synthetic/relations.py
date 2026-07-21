"""Build true_relations.parquet from latent_cycles.parquet (Phase 4.5).

v0.1 ontology (config/synthetic/recurrence_ontology_v0_1.yaml): every cycle
has exactly one outgoing edge — NEXT_CYCLE to cycle_number+1 of the same
need if a next cycle was realized, else NO_SUCCESSOR. Purely derived from
latent_cycles (no hidden state): a need's chain simply has no
cycle_number+1 row when cycles.py stopped it (successor draw failed, max
cycles reached, or the window boundary was hit) — relations.py does not
need to know which of those three reasons applied.

Layer 1 and Layer 2 must never receive this table (spec Phase 4.5).
"""
from __future__ import annotations

import pandas as pd


def build_true_relations(cycles: pd.DataFrame, scenario_id: str) -> pd.DataFrame:
    cycles = cycles.sort_values(["need_id_true", "cycle_number"]).reset_index(drop=True)
    rows = []
    for _, grp in cycles.groupby("need_id_true", sort=False):
        grp = grp.sort_values("cycle_number").reset_index(drop=True)
        for i in range(len(grp)):
            row = grp.iloc[i]
            if i + 1 < len(grp):
                nxt = grp.iloc[i + 1]
                gap_months = (nxt["start_date_true"] - row["expected_end_true"]).days / 30.44
                rows.append(dict(
                    source_cycle_id=row["cycle_id_true"],
                    target_cycle_id=nxt["cycle_id_true"],
                    relation_type="NEXT_CYCLE",
                    strict_label=True,
                    broad_label=True,
                    true_gap_months=gap_months,
                    source_expected_end=row["expected_end_true"],
                    target_start=nxt["start_date_true"],
                    scenario=scenario_id,
                ))
            else:
                rows.append(dict(
                    source_cycle_id=row["cycle_id_true"],
                    target_cycle_id=None,
                    relation_type="NO_SUCCESSOR",
                    strict_label=False,
                    broad_label=False,
                    true_gap_months=None,
                    source_expected_end=row["expected_end_true"],
                    target_start=None,
                    scenario=scenario_id,
                ))
    return pd.DataFrame(rows)
